"""程序说明：第十三阶段产品化测试，覆盖离线模式、安全观测、备份恢复与存档导出导入。"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.archive import backup_database, export_game, import_game, restore_database
from app.llm_model import ProviderModel
from app.main import build_model, create_app
from app.model import SimulatedModel
from app.provider_config import load_provider_config
from app.store import Database


LEGAL_ACTION = {
    "id": "inspect_fangsheng_room",
    "label": "查看方笙住处",
    "aliases": ["方笙住处"],
    "tendency": "洞察",
    "requires_roll": True,
    "modifier": 1,
}


def provider_env(**overrides):
    """生成最小可用 Provider 环境，密钥固定为测试值。"""
    values = {
        "AI_CURRENT_PROVIDER": "1",
        "AI_CURRENT_MODEL": "1.1",
        "AI_PROVIDER_1_NAME": "dashscope",
        "AI_PROVIDER_1_BASE_URL": "https://example.test/v1",
        "AI_PROVIDER_1_API_KEY": "phase13-secret-key",
        "AI_PROVIDER_1_TIMEOUT_SECONDS": "30",
        "AI_PROVIDER_1_MAX_RETRIES": "0",
        "AI_MODEL_1_1_NAME": "qwen-test",
    }
    values.update(overrides)
    return values


def completion(content):
    """构造 OpenAI 兼容成功响应。"""
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 6, "completion_tokens": 4},
        },
    )


def make_service(db_path):
    """建立只使用临时数据库的服务。"""
    from app.game import GameService

    database = Database(db_path).initialize()
    return GameService(database, SimulatedModel()), database


def play_three(service, game_id):
    """提交三次行动，产生可导出的历史与叙事。"""
    steps = (
        ("询问委托细节", "commission_details"),
        ("接受方笙的委托", "accept_commission"),
        ("前往新栖公寓", "travel_hc07"),
    )
    for index, (text, action_id) in enumerate(steps, 1):
        service.act(game_id, text, f"p13-{index}", action_id)


def test_offline_flag_forces_simulated_model(monkeypatch):
    """离线开关优先于完整 Provider 配置，确保无外部调用。"""
    for key, value in provider_env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("GREY_ZONE_OFFLINE", "1")
    assert isinstance(build_model(), SimulatedModel)


def test_health_reports_schema_without_secrets(tmp_path):
    """健康接口只暴露公开信息、schema 版本与统计。"""
    app = create_app(
        tmp_path / "health.db",
        model=SimulatedModel(),
        offline=True,
        log_dir=tmp_path / "logs",
    )
    payload = TestClient(app).get("/api/health").json()
    assert payload["status"] == "ok"
    assert payload["model"] == "simulated"
    assert payload["offline"] is True
    assert payload["schema_version"] == 8
    assert payload["database"] == "ok"
    assert payload["model_stats"]["requests"] == 0
    text = json.dumps(payload, ensure_ascii=False)
    assert "phase13-secret-key" not in text
    assert "base_url" not in text


def test_provider_health_hides_key_and_base_url(tmp_path):
    """在线模型健康信息只保留 Provider 名称与模型名。"""
    config = load_provider_config(environ=provider_env())
    model = ProviderModel(config, transport=httpx.MockTransport(lambda _: completion("ok")))
    app = create_app(tmp_path / "provider.db", model=model, log_dir=tmp_path / "logs")
    payload = TestClient(app).get("/api/health").json()
    assert payload["model"] == "provider"
    assert payload["provider"] == "dashscope"
    text = json.dumps(payload, ensure_ascii=False)
    assert "phase13-secret-key" not in text
    assert "example.test" not in text


def test_provider_stats_counts_failures_and_fallbacks():
    """调用统计区分成功、最终失败与本地回退。"""
    config = load_provider_config(environ=provider_env())

    def handler(request):
        if "行动解析器" in request.content.decode("utf-8"):
            return completion("不是 JSON")
        return completion("叙事文字")

    model = ProviderModel(config, transport=httpx.MockTransport(handler), sleep=lambda _: None)
    model.parse_action("看看方笙的房间", [LEGAL_ACTION])
    stats = model.stats()
    assert stats["requests"] == 1
    assert stats["failures"] == 0
    assert stats["fallbacks"] == 1

    failing = ProviderModel(
        config,
        transport=httpx.MockTransport(lambda _: httpx.Response(500, json={})),
        sleep=lambda _: None,
    )
    failing.parse_action("看看方笙的房间", [LEGAL_ACTION])
    stats = failing.stats()
    assert stats["requests"] == 1
    assert stats["failures"] == 1
    assert stats["fallbacks"] == 1


def test_structured_log_redacts_secret(tmp_path):
    """结构化日志逐行 JSON，且不包含 Provider 密钥。"""
    config = load_provider_config(environ=provider_env())
    model = ProviderModel(
        config,
        transport=httpx.MockTransport(lambda _: httpx.Response(401, json={} )),
        sleep=lambda _: None,
    )
    app = create_app(
        tmp_path / "log.db",
        model=model,
        log_dir=tmp_path / "logs",
        log_level="INFO",
    )
    client = TestClient(app)
    client.get("/api/health")
    model.parse_action("看看方笙的房间", [LEGAL_ACTION])

    log_files = list((tmp_path / "logs").glob("*.jsonl"))
    assert log_files
    text = "\n".join(path.read_text(encoding="utf-8") for path in log_files)
    assert "phase13-secret-key" not in text
    for line in text.splitlines():
        if line.strip():
            record = json.loads(line)
            assert "ts" in record and "level" in record and "message" in record


def test_backup_database_creates_integrity_checked_copy(tmp_path):
    """备份使用 SQLite 在线备份，并通过完整性检查。"""
    db_path = tmp_path / "games.db"
    service, database = make_service(db_path)
    game = service.create_game("江逢")
    backup = backup_database(db_path, tmp_path / "backups")
    assert backup.exists()
    with Database(backup).connect() as conn:
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT COUNT(*) FROM games WHERE id=?", (game["id"],)).fetchone()[0] == 1


def test_restore_requires_confirmation_and_keeps_safety_copy(tmp_path):
    """恢复必须显式确认，并在覆盖前保留当前库快照。"""
    db_path = tmp_path / "games.db"
    service, database = make_service(db_path)
    original = service.create_game("江逢")
    backup = backup_database(db_path, tmp_path / "backups")
    service.create_game("第二位")

    with pytest.raises(ValueError):
        restore_database(db_path, backup, confirm=False)

    result = restore_database(db_path, backup, confirm=True, backup_dir=tmp_path / "backups")
    assert result["restored_from"] == str(backup)
    assert result["safety_copy"]
    with Database(db_path).connect() as conn:
        rows = conn.execute("SELECT id FROM games").fetchall()
    assert [row[0] for row in rows] == [original["id"]]


def test_export_import_roundtrip_preserves_state_and_replay(tmp_path):
    """导出存档可导入到新库，案件状态、行动数与回放校验保持一致。"""
    source_path = tmp_path / "source.db"
    service, database = make_service(source_path)
    game = service.create_game("江逢")
    play_three(service, game["id"])
    payload = export_game(source_path, game["id"])
    assert payload["format"] == "grey-zone-save"
    assert payload["format_version"] == 1
    assert "phase13-secret-key" not in json.dumps(payload, ensure_ascii=False)

    target_path = tmp_path / "target.db"
    Database(target_path).initialize()
    imported = import_game(target_path, payload)
    imported_service, imported_db = make_service(target_path)

    assert imported["id"] != game["id"]
    source_state = database.get_case_state(game["id"])
    target_state = imported_db.get_case_state(imported["id"])
    assert target_state["phase"] == source_state["phase"]
    assert target_state["location"] == source_state["location"]
    assert target_state["revision"] == source_state["revision"]
    assert target_state["clues"] == source_state["clues"]
    assert imported_db.count_actions(imported["id"]) == database.count_actions(game["id"])
    assert imported_service.verify_replay(imported["id"])["status"] == "matched"


def test_export_import_keeps_player_hypotheses(tmp_path):
    """玩家假设随存档导出导入，不参与机械回放。"""
    source_path = tmp_path / "source.db"
    service, database = make_service(source_path)
    game = service.create_game("江逢")
    service.create_hypothesis(game["id"], "方笙在隐瞒排班")
    payload = export_game(source_path, game["id"])

    target_path = tmp_path / "target.db"
    Database(target_path).initialize()
    imported = import_game(target_path, payload)
    hypotheses = Database(target_path).get_hypotheses(imported["id"])
    assert [item["text"] for item in hypotheses] == ["方笙在隐瞒排班"]


def test_api_export_import_roundtrip(tmp_path):
    """接口导出后可直接导入，并返回新存档。"""
    app = create_app(
        tmp_path / "api.db",
        model=SimulatedModel(),
        offline=True,
        log_dir=tmp_path / "logs",
    )
    client = TestClient(app)
    game = client.post("/api/games", json={"protagonist": "江逢"}).json()
    for index, (text, action_id) in enumerate(
        (("接受方笙的委托", "accept_commission"), ("前往新栖公寓", "travel_hc07")), 1
    ):
        client.post(
            f"/api/games/{game['id']}/actions",
            json={"text": text, "action_id": action_id, "request_id": f"api-{index}"},
        )
    exported = client.get(f"/api/games/{game['id']}/export").json()
    response = client.post("/api/games/import", json=exported)
    assert response.status_code == 201
    imported = response.json()["game"]
    state = client.get(f"/api/games/{imported['id']}").json()["case"]
    assert state["phase"] == "active"
    assert state["location"] == "HC-07"


def test_import_rejects_unknown_format(tmp_path):
    """非法导出格式返回 422，不写入半成品存档。"""
    app = create_app(
        tmp_path / "bad.db",
        model=SimulatedModel(),
        offline=True,
        log_dir=tmp_path / "logs",
    )
    client = TestClient(app)
    response = client.post("/api/games/import", json={"format": "unknown", "format_version": 1})
    assert response.status_code == 422
