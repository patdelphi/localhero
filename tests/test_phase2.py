"""程序说明：验证第二阶段结构化事实、Clock、核心线索、人物认知、假设与 v3 迁移。"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.case_content import CLUE_DEFINITIONS
from app.game import GameService
from app.main import create_app
from app.model import SimulatedModel
from app.rules import RollResult
from app.store import Database


def make_service(tmp_path):
    """建立只使用临时数据库的第二阶段服务。"""
    db = Database(tmp_path / "phase2.db").initialize()
    return GameService(db, SimulatedModel()), db


def act(service, game_id, text, request_id):
    """使用固定请求标识执行行动，便于核对结构化记录。"""
    return service.act(game_id, text, request_id)


def test_facts_clock_and_knowledge_trace_to_committed_events(tmp_path):
    """事实、Clock 与玩家观察必须和同事务的来源事件关联。"""
    service, db = make_service(tmp_path)
    game = service.create_game("江逢")
    game_id = game["id"]

    act(service, game_id, "拒绝委托", "decline")
    act(service, game_id, "接受方笙的委托", "accept")

    facts = db.get_case_facts(game_id)
    commission = next(fact for fact in facts if fact["fact_id"] == "commission")
    assert commission["status"] == "active"
    assert commission["source_kind"] == "action_committed"

    changes = db.get_clock_changes(game_id)
    assert len(changes) == 1
    assert changes[0]["clock_id"] == "project_cleanup"
    assert (changes[0]["delta"], changes[0]["before_value"], changes[0]["after_value"]) == (1, 0, 1)
    assert changes[0]["source_kind"] == "action_committed"

    knowledge = db.get_player_knowledge(game_id)
    observation = next(item for item in knowledge if item["fact_id"] == "commission")
    assert observation["kind"] == "observation"
    assert observation["holder_id"] == "player"
    assert observation["source_event_id"] == commission["source_event_id"]


def test_duplicate_request_does_not_duplicate_structured_records(tmp_path):
    """幂等重放不得重复累计 Clock、事实或认知。"""
    service, db = make_service(tmp_path)
    game = service.create_game("江逢")

    first = act(service, game["id"], "拒绝委托", "same-decline")
    second = act(service, game["id"], "拒绝委托", "same-decline")

    assert first == second
    assert len(db.get_clock_changes(game["id"])) == 1
    assert db.get_case_state(game["id"])["clock"] == 1


def test_invalid_clock_change_rolls_back_entire_action(tmp_path):
    """前后值与增量不一致时，行动、事件和投影必须全部回滚。"""
    service, db = make_service(tmp_path)
    game = service.create_game("江逢")
    next_state = {
        "phase": "deferred",
        "location": "OC-01",
        "clock": 2,
        "clues": [],
        "ending": None,
    }
    changes = {
        "facts_add": [],
        "clock": {
            "clock_id": "project_cleanup",
            "reason": "测试不一致 Clock",
            "delta": 1,
            "before_value": 0,
            "after_value": 2,
        },
        "knowledge": [],
    }

    with pytest.raises(ValueError, match="前后值"):
        db.commit_action(
            game["id"],
            "broken-clock",
            "拒绝委托",
            {"kind": "case_action", "action_id": "decline_commission"},
            None,
            next_state,
            structured_changes=changes,
        )

    assert db.get_audit(game["id"]) == []
    assert len(db.get_events(game["id"])) == 1
    assert db.get_case_state(game["id"])["clock"] == 0
    assert db.get_clock_changes(game["id"]) == []


def test_clock_without_source_event_is_rejected(tmp_path):
    """显式缺失来源事件的 Clock 声明不能写入。"""
    service, db = make_service(tmp_path)
    game = service.create_game("江逢")
    next_state = {
        "phase": "deferred",
        "location": "OC-01",
        "clock": 1,
        "clues": [],
        "ending": None,
    }
    changes = {
        "facts_add": [],
        "clock": {
            "clock_id": "project_cleanup",
            "source_event_id": None,
            "reason": "无来源测试",
            "delta": 1,
            "before_value": 0,
            "after_value": 1,
        },
        "knowledge": [],
    }

    with pytest.raises(ValueError, match="来源事件"):
        db.commit_action(
            game["id"],
            "source-less-clock",
            "拒绝委托",
            {"kind": "case_action", "action_id": "decline_commission"},
            None,
            next_state,
            structured_changes=changes,
        )

    assert db.get_clock_changes(game["id"]) == []
    assert len(db.get_events(game["id"])) == 1


def test_clock_limit_does_not_automatically_close_case(tmp_path):
    """达到显示上限只表示压力到顶，不能替代明确结案行动。"""
    service, db = make_service(tmp_path)
    game = service.create_game("江逢")

    for index in range(4):
        act(service, game["id"], "拒绝委托", f"decline-{index}")

    case = service.get_game(game["id"])["case"]
    assert case["clock"] == 4
    assert case["phase"] == "deferred"
    assert case["ending"] is None


def test_invalidated_fact_immediately_revokes_action_permission(tmp_path):
    """事实失效保留历史，但对应行动权限必须立即消失。"""
    service, db = make_service(tmp_path)
    game = service.create_game("江逢")
    game_id = game["id"]
    act(service, game_id, "接受方笙的委托", "accept")
    act(service, game_id, "前往新栖公寓", "travel")
    act(service, game_id, "要求查看项目导出", "export")
    act(service, game_id, "核对共享排班", "shared")

    db.invalidate_fact(game_id, "shared_account", "测试事实失效")
    preview = service.preview_action(
        game_id, "当面质问邵谦", action_id="confront_shaoqian"
    )

    assert preview["can_submit"] is False
    fact = next(item for item in db.get_case_facts(game_id) if item["fact_id"] == "shared_account")
    assert fact["status"] == "invalidated"
    assert fact["source_event_id"] is not None
    assert fact["invalidated_event_id"] is not None
    assert "shared_account" not in db.get_case_state(game_id)["clues"]


def test_core_clues_have_authored_acquisition_and_alternative_paths():
    """核心线索必须声明固定获取方法及不完整结果的替代路径。"""
    shared = CLUE_DEFINITIONS["shared_account"]
    miaoyu = CLUE_DEFINITIONS["miaoyu_alive"]

    assert shared["priority"] == "necessary"
    assert any(path["action_id"] == "check_shared_account" for path in shared["acquisition"])
    assert any(path["via"] == "export_delayed" for path in shared["alternatives"])
    assert miaoyu["priority"] == "necessary"
    assert any(path["via"] == "manifest_alternative" for path in miaoyu["alternatives"])


def test_escalation_export_alternative_unlocks_shared_account(tmp_path, monkeypatch):
    """项目导出坏骰只留下延迟记录时，仍必须能取得共享账户核心事实。"""
    monkeypatch.setattr(
        "app.game.roll_for_sequence",
        lambda seed, sequence, modifier: RollResult((1, 1), modifier, "escalation"),
    )
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    act(service, game_id, "接受方笙的委托", "accept")
    act(service, game_id, "前往新栖公寓", "travel")
    act(service, game_id, "要求查看项目导出", "export")

    fact_ids = {fact["fact_id"] for fact in db.get_case_facts(game_id)}
    assert "export_delayed" in fact_ids
    assert "project_export" not in fact_ids
    preview = service.preview_action(
        game_id, "核对共享排班", action_id="check_shared_account"
    )
    assert preview["can_submit"] is True

    act(service, game_id, "核对共享排班", "shared")
    fact_ids = {fact["fact_id"] for fact in db.get_case_facts(game_id)}
    assert "shared_account" in fact_ids
    assert "shared_account" in db.get_case_state(game_id)["clues"]


def test_escalation_manifest_alternative_unlocks_miaoyu(tmp_path, monkeypatch):
    """货运签坏骰只留下残缺方向时，仍必须能确认苗雨仍在世。"""
    monkeypatch.setattr(
        "app.game.roll_for_sequence",
        lambda seed, sequence, modifier: RollResult((1, 1), modifier, "escalation"),
    )
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    act(service, game_id, "接受方笙的委托", "accept")
    act(service, game_id, "前往青苔诊所", "clinic")
    act(service, game_id, "询问匿名患者", "patient")
    act(service, game_id, "前往白绳货运场", "freight")
    act(service, game_id, "查询短驳记录", "manifest")

    fact_ids = {fact["fact_id"] for fact in db.get_case_facts(game_id)}
    assert "manifest_alternative" in fact_ids
    assert "freight_manifest" not in fact_ids
    preview = service.preview_action(
        game_id, "联系阿洛药摊确认苗雨", action_id="contact_miaoyu"
    )
    assert preview["can_submit"] is True

    act(service, game_id, "联系阿洛药摊确认苗雨", "contact")
    fact_ids = {fact["fact_id"] for fact in db.get_case_facts(game_id)}
    assert "miaoyu_alive" in fact_ids
    assert "miaoyu_alive" in db.get_case_state(game_id)["clues"]


def test_misleading_testimony_does_not_create_admission_fact(tmp_path, monkeypatch):
    """邵谦局势升级时的误导证词只能进入人物认知，不能升级为承认事实。"""
    monkeypatch.setattr(
        "app.game.roll_for_sequence",
        lambda seed, sequence, modifier: RollResult((1, 1), modifier, "escalation"),
    )
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    act(service, game_id, "接受方笙的委托", "accept")
    act(service, game_id, "前往新栖公寓", "travel")
    act(service, game_id, "要求查看项目导出", "export")
    act(service, game_id, "核对共享排班", "shared")
    act(service, game_id, "当面质问邵谦", "confront")

    testimony = [
        item for item in db.get_player_knowledge(game_id)
        if item["holder_id"] == "shao_qian"
    ]
    assert len(testimony) == 1
    assert testimony[0]["kind"] == "testimony"
    assert testimony[0]["accuracy"] == "misleading"
    assert testimony[0]["fact_id"] is None
    assert "shaqian_admission" not in {
        fact["fact_id"] for fact in db.get_case_facts(game_id)
    }
    assert "shaqian_admission" not in db.get_case_state(game_id)["clues"]


def test_player_knowledge_separates_observation_and_testimony(tmp_path):
    """同一来源事件可产生玩家观察和人物证词，接口只返回玩家可见记录。"""
    service, db = make_service(tmp_path)
    game = service.create_game("江逢")
    game_id = game["id"]
    act(service, game_id, "接受方笙的委托", "accept")
    act(service, game_id, "前往青苔诊所", "travel")
    act(service, game_id, "询问匿名患者", "ask")

    knowledge = db.get_player_knowledge(game_id)
    assert {item["kind"] for item in knowledge} >= {"observation", "testimony"}
    assert any(item["holder_id"] == "lin_yanzhou" for item in knowledge)
    assert all(item["visibility"] == "player" for item in knowledge)


def test_invalid_knowledge_kind_rolls_back_action(tmp_path):
    """非法认知类型不能留下部分行动或事件。"""
    service, db = make_service(tmp_path)
    game = service.create_game("江逢")
    changes = {
        "facts_add": [],
        "clock": None,
        "knowledge": [{
            "holder_id": "player",
            "kind": "secret",
            "fact_id": None,
            "content": "非法秘密知识",
            "accuracy": "unknown",
            "visibility": "player",
        }],
    }

    with pytest.raises(sqlite3.IntegrityError):
        db.commit_action(
            game["id"],
            "invalid-knowledge",
            "普通观察",
            {"kind": "improvise"},
            None,
            structured_changes=changes,
        )

    assert db.get_audit(game["id"]) == []
    assert len(db.get_events(game["id"])) == 1


def test_hypothesis_crud_does_not_change_game_state(tmp_path):
    """玩家假设增删改不得产生事件、推进 revision 或消耗随机序号。"""
    client = TestClient(create_app(tmp_path / "hypotheses.db", model=SimulatedModel()))
    game_id = client.post("/api/games", json={"protagonist": "江逢"}).json()["id"]
    before = client.get(f"/api/games/{game_id}").json()

    created = client.post(
        f"/api/games/{game_id}/hypotheses", json={"text": "苗雨仍在使用旧凭证"}
    )
    assert created.status_code == 201
    hypothesis_id = created.json()["id"]

    updated = client.patch(
        f"/api/games/{game_id}/hypotheses/{hypothesis_id}",
        json={"text": "苗雨的凭证被共享账户复用"},
    )
    assert updated.status_code == 200
    assert updated.json()["text"] == "苗雨的凭证被共享账户复用"

    listed = client.get(f"/api/games/{game_id}/hypotheses")
    assert [item["id"] for item in listed.json()["items"]] == [hypothesis_id]
    deleted = client.delete(f"/api/games/{game_id}/hypotheses/{hypothesis_id}")
    assert deleted.status_code == 204

    after = client.get(f"/api/games/{game_id}").json()
    assert len(after["events"]) == len(before["events"])
    assert after["case"]["revision"] == before["case"]["revision"]
    assert after["game"]["roll_count"] == before["game"]["roll_count"]


def test_hypothesis_validation_and_cross_game_isolation(tmp_path):
    """空文本、跨存档修改和不存在记录必须被拒绝。"""
    client = TestClient(create_app(tmp_path / "hypothesis-errors.db", model=SimulatedModel()))
    first_id = client.post("/api/games", json={"protagonist": "江逢"}).json()["id"]
    second_id = client.post("/api/games", json={"protagonist": "唐葵"}).json()["id"]
    hypothesis_id = client.post(
        f"/api/games/{first_id}/hypotheses", json={"text": "初始假设"}
    ).json()["id"]

    assert client.post(f"/api/games/{first_id}/hypotheses", json={"text": "  "}).status_code == 422
    assert client.patch(
        f"/api/games/{second_id}/hypotheses/{hypothesis_id}", json={"text": "越权修改"}
    ).status_code == 404
    assert client.delete(f"/api/games/{second_id}/hypotheses/{hypothesis_id}").status_code == 404
    assert client.delete(f"/api/games/{first_id}/hypotheses/missing").status_code == 404
    assert client.get(f"/api/games/{first_id}/knowledge").status_code == 200


def test_preview_declares_mechanical_changes_without_writing(tmp_path):
    """预览应展示各判定结果的事实、Clock 与认知摘要，但不写结构化记录。"""
    service, db = make_service(tmp_path)
    game = service.create_game("江逢")

    preview = service.preview_action(
        game["id"], "拒绝委托", action_id="decline_commission"
    )

    assert preview["mechanical_changes"][0]["clock"]["delta"] == 1
    assert db.get_clock_changes(game["id"]) == []
    assert db.get_case_facts(game["id"]) == []
    assert db.get_player_knowledge(game["id"]) == []


def test_v2_migration_backups_backfills_and_is_idempotent(tmp_path):
    """v2 快照迁移保留备份，只回填当前事实、Clock 与未知准确性记忆。"""
    path = tmp_path / "v2.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE games (
                id TEXT PRIMARY KEY, protagonist TEXT NOT NULL, location TEXT NOT NULL,
                seed INTEGER NOT NULL, roll_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE actions (
                id TEXT PRIMARY KEY, game_id TEXT NOT NULL REFERENCES games(id),
                request_id TEXT NOT NULL, request_hash TEXT, input_text TEXT NOT NULL,
                command_json TEXT, intent_json TEXT NOT NULL, declaration_json TEXT,
                audit_json TEXT, roll_json TEXT, rules_version TEXT, content_version TEXT,
                status TEXT NOT NULL, response_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, completed_at TEXT,
                UNIQUE(game_id, request_id)
            );
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL REFERENCES games(id), action_id TEXT,
                kind TEXT NOT NULL, payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE case_states (
                game_id TEXT PRIMARY KEY REFERENCES games(id), phase TEXT NOT NULL,
                location TEXT NOT NULL, clock INTEGER NOT NULL DEFAULT 0,
                clues_json TEXT NOT NULL DEFAULT '[]', ending TEXT,
                revision INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO games(id, protagonist, location, seed) VALUES ('g1', '江逢', 'HC-07', 1);
            INSERT INTO case_states(game_id, phase, location, clock, clues_json, revision)
            VALUES ('g1', 'active', 'HC-07', 2, '["commission", "project_export"]', 7);
            PRAGMA user_version=2;
            """
        )

    db = Database(path).initialize()
    backup_path = tmp_path / "v2.db.pre-v3.bak"
    assert backup_path.exists()
    backup_bytes = backup_path.read_bytes()
    with sqlite3.connect(backup_path) as backup:
        assert backup.execute("PRAGMA user_version").fetchone()[0] == 2

    assert db.get_case_state("g1")["revision"] == 7
    assert {fact["fact_id"] for fact in db.get_case_facts("g1")} == {
        "commission", "project_export"
    }
    snapshot = db.get_clock_changes("g1")[0]
    assert (snapshot["delta"], snapshot["before_value"], snapshot["after_value"]) == (0, 2, 2)
    memories = db.get_player_knowledge("g1")
    assert {item["kind"] for item in memories} == {"memory"}
    assert {item["accuracy"] for item in memories} == {"unknown"}
    counts = (
        len(db.get_events("g1")),
        len(db.get_case_facts("g1")),
        len(db.get_clock_changes("g1")),
        len(memories),
    )

    Database(path).initialize()
    assert backup_path.read_bytes() == backup_bytes
    assert counts == (
        len(db.get_events("g1")),
        len(db.get_case_facts("g1")),
        len(db.get_clock_changes("g1")),
        len(db.get_player_knowledge("g1")),
    )
    assert sum(event["kind"] == "legacy_v3_backfill" for event in db.get_events("g1")) == 1
