"""程序说明：提供仅绑定本地使用的 FastAPI 预览、行动、审计和叙事重试接口。"""

import os
from pathlib import Path
import sqlite3

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.action_protocol import ActionConflict, PermissionDenied
from app.game import GameService
from app.model import SimulatedModel, SimulationError
from app.store import Database


class CreateGameRequest(BaseModel):
    """新存档只需要轻量主人公姓名。"""

    protagonist: str = Field(default="江逢", max_length=40)


class PreviewRequest(BaseModel):
    """预览不需要请求标识，也不能携带随机或写入指令。"""

    text: str = Field(max_length=2000)
    action_id: str | None = Field(default=None, max_length=100)


class ActionRequest(PreviewRequest):
    """请求标识用于幂等，状态版本用于拒绝过期提交。"""

    request_id: str = Field(min_length=1, max_length=80)
    expected_revision: int | None = Field(default=None, ge=0)


def create_app(db_path: str | Path, model: SimulatedModel | None = None) -> FastAPI:
    """创建可注入临时数据库和模拟模型的应用，便于隔离测试。"""
    service = GameService(Database(db_path).initialize(), model or SimulatedModel())
    app = FastAPI(title="灰区事务所", version="0.2.0")
    app.state.service = service

    @app.exception_handler(KeyError)
    async def handle_not_found(_, exc: KeyError):
        return JSONResponse(status_code=404, content={"detail": "资源不存在"})

    @app.exception_handler(ValueError)
    async def handle_validation(_, exc: ValueError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(PermissionDenied)
    async def handle_permission(_, exc: PermissionDenied):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(ActionConflict)
    async def handle_conflict(_, exc: ActionConflict):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(SimulationError)
    async def handle_simulation(_, exc: SimulationError):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(sqlite3.Error)
    async def handle_database(_, exc: sqlite3.Error):
        return JSONResponse(status_code=500, content={"detail": "存档写入或读取失败"})

    @app.get("/api/health")
    def health():
        """健康检查不调用模型，也不产生外部请求。"""
        return {"status": "ok", "model": "simulated"}

    @app.post("/api/games", status_code=201)
    def create_game(request: CreateGameRequest):
        return service.create_game(request.protagonist)

    @app.get("/api/games/{game_id}")
    def get_game(game_id: str):
        return service.get_game(game_id)

    @app.post("/api/games/{game_id}/actions/preview")
    def preview_action(game_id: str, request: PreviewRequest):
        return service.preview_action(game_id, request.text, request.action_id)

    @app.post("/api/games/{game_id}/actions")
    def act(game_id: str, request: ActionRequest):
        result = service.act(
            game_id,
            request.text,
            request.request_id,
            request.action_id,
            request.expected_revision,
        )
        if result["status"] == "narrative_pending":
            return JSONResponse(status_code=202, content=result)
        return result

    @app.get("/api/games/{game_id}/audit")
    def get_audit(game_id: str, limit: int = Query(default=50, ge=1, le=100)):
        return service.get_audit(game_id, limit)

    @app.post("/api/games/{game_id}/actions/{action_id}/retry")
    def retry_narrative(game_id: str, action_id: str):
        result = service.retry_narrative(game_id, action_id)
        if result["status"] == "narrative_pending":
            return JSONResponse(status_code=202, content=result)
        return result

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(static_dir / "index.html")

    return app


app = create_app(os.getenv("GREY_ZONE_DB", "data/games.db"))
