"""程序说明：提供仅绑定本地使用的 FastAPI 预览、行动、审计和叙事重试接口。"""

import logging
import os
from pathlib import Path
import sqlite3

from fastapi import Body, FastAPI, Query, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.action_protocol import ActionConflict, PermissionDenied
from app.archive import export_game, import_game
from app.case_registry import list_cases
from app.game import GameService
from app.llm_model import ProviderModel
from app.logging_setup import configure_logging
from app.model import SimulatedModel, SimulationError
from app.provider_config import load_director_settings, load_provider_config
from app.store import Database

logger = logging.getLogger("localhero.llm")


class CreateGameRequest(BaseModel):
    """新存档只需要轻量主人公姓名。"""

    protagonist: str = Field(default="江逢", max_length=40)
    case_id: str | None = Field(default=None, max_length=20)


class PreviewRequest(BaseModel):
    """预览不需要请求标识，也不能携带随机或写入指令。"""

    text: str = Field(max_length=2000)
    action_id: str | None = Field(default=None, max_length=100)


class ActionRequest(PreviewRequest):
    """请求标识用于幂等，状态版本用于拒绝过期提交。"""

    request_id: str = Field(min_length=1, max_length=80)
    expected_revision: int | None = Field(default=None, ge=0)


class ReplayRequest(BaseModel):
    """可选目标行动用于把机械校验限制在历史前缀。"""

    through_action_id: str | None = Field(default=None, max_length=100)


class HypothesisRequest(BaseModel):
    """玩家假设只包含可编辑文本，不接受机械状态字段。"""

    text: str = Field(max_length=4000)


class BranchRequest(BaseModel):
    """分叉点必须是该存档已记录的行动。"""

    fork_action_id: str = Field(min_length=1, max_length=100)
    label: str | None = Field(default=None, max_length=40)


class BranchStatusRequest(BaseModel):
    """归档或恢复分支必须显式确认。"""

    confirm: bool = False


class DirectorRequest(BaseModel):
    """情节导演开关只接受布尔值，不写存档。"""

    enabled: bool


def build_model(offline: bool | None = None):
    """按配置构建模型；离线开关优先于 Provider，确保无外部调用。"""
    if offline is None:
        offline = os.getenv("GREY_ZONE_OFFLINE", "").strip().lower() in {
            "1", "true", "yes", "on",
        }
    if offline:
        return SimulatedModel()
    try:
        config = load_provider_config()
    except ValueError as exc:
        logger.warning("在线 Provider 配置无效，使用模拟模型：%s", exc)
        return SimulatedModel()
    if config is None:
        return SimulatedModel()
    return ProviderModel(config, fallback=SimulatedModel())


def create_app(
    db_path: str | Path,
    model=None,
    director_enabled: bool | None = None,
    director_interval: int | None = None,
    offline: bool | None = None,
    log_dir: str | Path | None = None,
    log_level: str | None = None,
) -> FastAPI:
    """创建可注入临时数据库和模型的应用，便于隔离测试。"""
    configure_logging(log_dir, log_level)
    env_enabled, env_interval = load_director_settings()
    service = GameService(
        Database(db_path).initialize(),
        model or build_model(offline),
        director_enabled=env_enabled if director_enabled is None else director_enabled,
        director_interval=env_interval if director_interval is None else director_interval,
    )
    app = FastAPI(title="灰区事务所", version="1.0.0")
    app.state.service = service
    app.state.offline = isinstance(service.model, SimulatedModel)

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
        """健康检查不调用模型，只报告公开配置、schema 与调用统计。"""
        version = None
        database_status = "ok"
        try:
            with service.db.connect() as conn:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                conn.execute("SELECT 1")
        except sqlite3.Error:
            database_status = "error"
        stats = service.model.stats() if hasattr(service.model, "stats") else {}
        payload = {
            "status": "ok",
            "model": "provider" if isinstance(service.model, ProviderModel) else "simulated",
            "offline": app.state.offline,
            "schema_version": version,
            "database": database_status,
            "model_stats": stats,
        }
        if isinstance(service.model, ProviderModel):
            payload.update(service.model.public_info())
        return payload

    @app.get("/api/games/{game_id}/export")
    def export_save(game_id: str):
        """导出单个存档；内容不含密钥与运行环境信息。"""
        return export_game(service.db.path, game_id)

    @app.post("/api/games/import", status_code=201)
    def import_save(payload: dict = Body(...)):
        """导入导出文件，重建为全新存档；失败时不留下半成品。"""
        return {"game": import_game(service.db.path, payload)}

    @app.get("/api/cases")
    def get_cases():
        """返回可选案件目录，不包含隐藏真相或内部评分。"""
        return {"items": list_cases()}

    @app.post("/api/games", status_code=201)
    def create_game(request: CreateGameRequest):
        return service.create_game(request.protagonist, request.case_id)

    @app.get("/api/games/{game_id}")
    def get_game(game_id: str):
        return service.get_game(game_id)

    @app.get("/api/games/{game_id}/city")
    def get_city(game_id: str):
        """返回城市切片；只含公开日程，不返回隐藏真相。"""
        return service.get_city(game_id)

    @app.post("/api/games/{game_id}/branches")
    def create_branch(game_id: str, request: BranchRequest):
        """从指定行动分叉；原存档保持不变。"""
        return {
            "game": service.create_branch(
                game_id, request.fork_action_id, request.label
            )
        }

    @app.get("/api/games/{game_id}/branches")
    def get_branches(game_id: str):
        """返回分支树与各节点关键状态摘要。"""
        return service.get_branches(game_id)

    @app.post("/api/games/{branch_id}/branch/archive")
    def archive_branch(branch_id: str, request: BranchStatusRequest):
        """归档分支；数据保留并可恢复。"""
        return {
            "game": service.set_branch_status(branch_id, "archived", request.confirm)
        }

    @app.post("/api/games/{branch_id}/branch/restore")
    def restore_branch(branch_id: str, request: BranchStatusRequest):
        """恢复已归档分支。"""
        return {
            "game": service.set_branch_status(branch_id, "active", request.confirm)
        }

    @app.get("/api/games/{game_id}/timeline")
    def get_timeline(game_id: str):
        return service.get_timeline(game_id)

    @app.post("/api/games/{game_id}/replay/verify")
    def verify_replay(game_id: str, request: ReplayRequest):
        return service.verify_replay(game_id, request.through_action_id)

    @app.get("/api/games/{game_id}/knowledge")
    def get_knowledge(game_id: str):
        return service.get_knowledge(game_id)

    @app.get("/api/games/{game_id}/character-history")
    def get_character_history(game_id: str):
        return service.get_character_history(game_id)

    @app.get("/api/games/{game_id}/hypotheses")
    def get_hypotheses(game_id: str):
        return service.get_hypotheses(game_id)

    @app.post("/api/games/{game_id}/hypotheses", status_code=201)
    def create_hypothesis(game_id: str, request: HypothesisRequest):
        return service.create_hypothesis(game_id, request.text)

    @app.patch("/api/games/{game_id}/hypotheses/{hypothesis_id}")
    def update_hypothesis(game_id: str, hypothesis_id: str, request: HypothesisRequest):
        return service.update_hypothesis(game_id, hypothesis_id, request.text)

    @app.delete("/api/games/{game_id}/hypotheses/{hypothesis_id}", status_code=204)
    def delete_hypothesis(game_id: str, hypothesis_id: str):
        service.delete_hypothesis(game_id, hypothesis_id)
        return Response(status_code=204)

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

    @app.get("/api/games/{game_id}/director")
    def get_director_settings(game_id: str):
        return service.get_director_settings(game_id)

    @app.post("/api/games/{game_id}/director")
    def set_director_settings(game_id: str, request: DirectorRequest):
        return service.set_director_enabled(game_id, request.enabled)

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
