"""程序说明：验证本地 HTTP 接口的健康、存档、行动和异常边界。"""

from fastapi.testclient import TestClient

from app.main import create_app
from app.model import SimulatedModel


def make_client(tmp_path, model=None):
    """建立不访问外部服务的测试客户端。"""
    app = create_app(tmp_path / "game.db", model=model or SimulatedModel())
    return TestClient(app)


def test_health_and_complete_action_flow(tmp_path):
    """创建、行动、读取和历史应形成完整本地闭环。"""
    client = make_client(tmp_path)
    assert client.get("/api/health").status_code == 200

    created = client.post("/api/games", json={"protagonist": "江逢"})
    assert created.status_code == 201
    game_id = created.json()["id"]

    acted = client.post(
        f"/api/games/{game_id}/actions",
        json={"text": "查看现场", "request_id": "request-1"},
    )
    assert acted.status_code == 200
    assert acted.json()["status"] == "complete"

    loaded = client.get(f"/api/games/{game_id}")
    assert loaded.status_code == 200
    assert loaded.json()["game"]["id"] == game_id
    # 开场、行动、案件变化与城市离屏摘要各一条。
    assert len(loaded.json()["events"]) == 4


def test_narrative_failure_can_be_retried(tmp_path):
    """接口应保留已提交事实，并允许单独重试叙事。"""
    client = make_client(tmp_path, SimulatedModel(fail_narrative_times=1))
    game_id = client.post("/api/games", json={"protagonist": "江逢"}).json()["id"]

    pending = client.post(
        f"/api/games/{game_id}/actions",
        json={"text": "检查终端", "request_id": "request-1"},
    )
    assert pending.status_code == 202
    action_id = pending.json()["action_id"]

    retried = client.post(f"/api/games/{game_id}/actions/{action_id}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "complete"
    assert retried.json()["roll"] == pending.json()["roll"]


def test_invalid_input_and_missing_game_return_clear_errors(tmp_path):
    """空输入和不存在存档必须返回明确客户端错误。"""
    client = make_client(tmp_path)
    game_id = client.post("/api/games", json={"protagonist": "江逢"}).json()["id"]

    empty = client.post(
        f"/api/games/{game_id}/actions",
        json={"text": "  ", "request_id": "request-empty"},
    )
    missing = client.get("/api/games/not-found")

    assert empty.status_code == 422
    assert missing.status_code == 404
