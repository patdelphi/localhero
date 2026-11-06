"""程序说明：第十阶段案件注册表、C02《最后一班配送》与跨案关联测试。"""

import pytest
from fastapi.testclient import TestClient

from app.case_registry import get_case, list_cases
from app.game import GameService
from app.main import create_app
from app.model import SimulatedModel
from app.store import Database


def make_service(tmp_path, model=None):
    """创建只使用临时数据库的服务，避免触碰真实存档。"""
    db = Database(tmp_path / "phase10.db").initialize()
    return GameService(db, model or SimulatedModel()), db


def act(service, game_id, text, index):
    """使用稳定请求标识执行一次行动。"""
    return service.act(game_id, text, f"p10-{index}")


def test_registry_lists_two_cases_and_keeps_c01_version():
    """注册表能列出两案，且 C01 内容版本保持原值。"""
    cases = list_cases()
    ids = {item["case_id"] for item in cases}
    assert {"C01", "C02"} <= ids
    assert get_case("C01").content_version == "c01-1.3"
    assert get_case("C02").content_version == "c02-1.0"


def test_unknown_case_is_rejected():
    """未知案件编号不能被静默当成 C01。"""
    with pytest.raises(ValueError):
        get_case("C99")


def test_default_game_is_c01_and_c02_has_own_metadata(tmp_path):
    """默认新档仍是 C01；指定 C02 时读取案件标题与时钟上限。"""
    service, db = make_service(tmp_path)
    c01_id = service.create_game("江逢")["id"]
    c02_id = service.create_game("江逢", "C02")["id"]

    c01 = service.get_game(c01_id)
    c02 = service.get_game(c02_id)
    assert c01["game"]["case_id"] == "C01"
    assert c01["case"]["case_title"] == "不存在的人"
    assert c01["case"]["clock_max"] == 4

    assert c02["game"]["case_id"] == "C02"
    assert c02["case"]["case_title"] == "最后一班配送"
    assert c02["case"]["clock_max"] == 3
    assert c02["case"]["location"] == "OC-01"


def test_v6_database_gains_case_id_with_backup(tmp_path):
    """旧库升级到 v7 时补 case_id，默认 C01，并保留升级前备份。"""
    db = Database(tmp_path / "legacy.db").initialize()
    game_id = db.create_game("江逢")["id"]
    with db.transaction() as conn:
        conn.execute("ALTER TABLE games DROP COLUMN case_id")
        conn.execute("PRAGMA user_version=6")

    Database(db.path).initialize()

    assert db.path.with_name(f"{db.path.name}.pre-v7.bak").exists()
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 8
        row = conn.execute("SELECT case_id FROM games WHERE id=?", (game_id,)).fetchone()
    assert row[0] == "C01"


def test_c02_personal_reinstatement_ending(tmp_path):
    """C02 个人复职结局可达，且线索与地点连续。"""
    service, _ = make_service(tmp_path)
    game_id = service.create_game("江逢", "C02")["id"]

    act(service, game_id, "接受零工互助会的委托", 1)
    act(service, game_id, "前往栖光里", 2)
    act(service, game_id, "调取配送终端记录", 3)
    act(service, game_id, "前往零工互助站", 4)
    act(service, game_id, "核对周弥的存储片", 5)
    act(service, game_id, "前往安澜工程调度点", 6)
    act(service, game_id, "核对手动保持日志", 7)
    act(service, game_id, "选择个人复职", 8)

    case = service.get_game(game_id)["case"]
    assert case["phase"] == "closed"
    assert case["ending"] == "个人复职"
    assert {"delivery_terminal", "storage_fragment", "manual_hold_log"} <= {
        clue["id"] for clue in case["clues"]
    }


def test_c02_safety_pause_ending(tmp_path):
    """C02 安全暂停结局依赖手动保持与地图版本差异。"""
    service, _ = make_service(tmp_path)
    game_id = service.create_game("江逢", "C02")["id"]

    act(service, game_id, "接受零工互助会的委托", 1)
    act(service, game_id, "前往安澜工程调度点", 2)
    act(service, game_id, "核对手动保持日志", 3)
    act(service, game_id, "对照地图版本", 4)
    act(service, game_id, "推动安全暂停", 5)

    case = service.get_game(game_id)["case"]
    assert case["ending"] == "安全暂停"
    assert {"manual_hold_log", "map_version_gap"} <= {
        clue["id"] for clue in case["clues"]
    }


def test_c02_collective_bargaining_and_cross_case_clue(tmp_path):
    """C02 集体谈判结局可达，清洁日志线索带 C01 跨案标记。"""
    service, _ = make_service(tmp_path)
    game_id = service.create_game("江逢", "C02")["id"]

    act(service, game_id, "接受零工互助会的委托", 1)
    act(service, game_id, "前往栖光里", 2)
    act(service, game_id, "询问夜班商户", 3)
    act(service, game_id, "调取配送终端记录", 4)
    act(service, game_id, "前往零工互助站", 5)
    act(service, game_id, "核对周弥的存储片", 6)
    act(service, game_id, "追查路线清洁日志", 7)
    act(service, game_id, "发起集体谈判", 8)

    case = service.get_game(game_id)["case"]
    assert case["ending"] == "集体谈判"
    trace = next(clue for clue in case["clues"] if clue["id"] == "legacy_credential_trace")
    assert trace["cross_case"]["case_id"] == "C01"


def test_c02_cannot_execute_c01_action(tmp_path):
    """C02 存档不能借 C01 固定行动推进案件。"""
    service, _ = make_service(tmp_path)
    game_id = service.create_game("江逢", "C02")["id"]

    preview = service.preview_action(game_id, "接受方笙的委托")
    assert preview["selected_action"]["action_id"] != "accept_commission"
    assert preview["case_action"] is False


def test_case_catalog_and_c02_api(tmp_path):
    """接口可列出案件，并按 case_id 创建 C02 存档；非法编号返回 422。"""
    client = TestClient(create_app(tmp_path / "api.db", SimulatedModel()))

    catalog = client.get("/api/cases")
    assert catalog.status_code == 200
    assert {item["case_id"] for item in catalog.json()["items"]} >= {"C01", "C02"}

    created = client.post("/api/games", json={"protagonist": "江逢", "case_id": "C02"})
    assert created.status_code == 201
    detail = client.get(f"/api/games/{created.json()['id']}")
    assert detail.status_code == 200
    assert detail.json()["game"]["case_id"] == "C02"

    invalid = client.post("/api/games", json={"protagonist": "江逢", "case_id": "C99"})
    assert invalid.status_code == 422


def test_c02_replay_matches(tmp_path):
    """C02 行动可按案件内容确定性回放。"""
    service, _ = make_service(tmp_path)
    game_id = service.create_game("江逢", "C02")["id"]

    act(service, game_id, "接受零工互助会的委托", 1)
    act(service, game_id, "前往栖光里", 2)
    act(service, game_id, "查看碰撞现场", 3)

    result = service.verify_replay(game_id)
    assert result["status"] == "matched"
