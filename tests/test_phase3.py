"""程序说明：验证第三阶段社会状态、同源履历、固定计划、行动耗时与 v4 迁移。"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.game import GameService
from app.main import create_app
from app.model import SimulatedModel
from app.store import Database


def make_service(tmp_path):
    """建立仅使用临时数据库的第三阶段服务。"""
    db = Database(tmp_path / "phase3.db").initialize()
    return GameService(db, SimulatedModel()), db


def act(service, game_id, text, request_id, action_id=None):
    """以固定请求标识提交行动，便于验证幂等和来源事件。"""
    return service.act(game_id, text, request_id, action_id=action_id)


def start_reassurance(service, game_id):
    """走到首次安抚后：游戏时间为 1，固定计划应在 3 到期。"""
    act(service, game_id, "接受方笙的委托", "accept")
    return act(service, game_id, "安抚方笙", "reassure", "reassure_fangsheng")


def test_complete_social_chain_derives_history_and_fixed_testimony(tmp_path):
    """完整 C01 链应推进固定时间，到期只产生证词与履历，不产生核心事实。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]

    start_reassurance(service, game_id)
    case = service.get_game(game_id)["case"]
    assert case["world_time"] == 1
    assert case["plans"] == [{
        "plan_id": "fangsheng_followup",
        "holder_id": "fang_sheng",
        "due_time": 3,
        "status": "pending",
    }]

    states = {item["state_id"]: item for item in db.get_social_states(game_id)}
    trust = states["fang_sheng:player:trust"]
    assert trust["value_int"] == 1
    assert trust["visibility"] == "private"
    assert states["fang_sheng:player:relationship"]["value_text"] == "委托人"
    memory = next(
        item for item in db.get_character_history(game_id, include_private=True)
        if item["kind"] == "social_memory"
    )
    assert memory["source_event_id"] == trust["source_event_id"]
    assert memory["structured"]["state_id"] == trust["state_id"]

    act(service, game_id, "前往新栖公寓", "travel")
    assert db.get_local_plans(game_id)[0]["status"] == "pending"
    facts_before = {item["fact_id"] for item in db.get_case_facts(game_id)}
    act(service, game_id, "查看方笙住处", "inspect")

    plan = db.get_local_plans(game_id)[0]
    assert plan["status"] == "completed"
    assert plan["completed_event_id"] is not None
    assert db.get_case_state(game_id)["world_time"] == 3
    assert {item["fact_id"] for item in db.get_case_facts(game_id)} == (
        facts_before | {"fangsheng_present"}
    )
    testimony = next(
        item for item in db.get_player_knowledge(game_id)
        if "共享账户备注" in item["content"]
    )
    assert testimony["kind"] == "testimony"
    assert testimony["accuracy"] == "honest"
    assert testimony["fact_id"] is None
    events = db.get_events(game_id)
    completion_event = next(event for event in events if event["id"] == plan["completed_event_id"])
    assert completion_event["kind"] == "local_simulation_advanced"
    assert testimony["source_event_id"] == completion_event["id"]


def test_reassurance_is_directional_bounded_and_not_stacked(tmp_path):
    """重复安抚只耗时；反向信任、历史数量与固定计划均不得叠加。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    start_reassurance(service, game_id)
    counts = (
        len(db.get_social_states(game_id)),
        len(db.get_character_history(game_id, include_private=True)),
        len(db.get_local_plans(game_id)),
    )

    act(service, game_id, "再次安抚方笙", "reassure-again", "reassure_fangsheng")

    assert db.get_case_state(game_id)["world_time"] == 2
    assert counts == (
        len(db.get_social_states(game_id)),
        len(db.get_character_history(game_id, include_private=True)),
        len(db.get_local_plans(game_id)),
    )
    states = db.get_social_states(game_id)
    assert not any(item["state_id"] == "player:fang_sheng:trust" for item in states)
    assert all(item["kind"] != "trust" or -2 <= item["value_int"] <= 2 for item in states)


def test_condition_expires_after_plan_and_history_is_retained(tmp_path):
    """短期状态在到期前保持，到期后保留投影及全部历史。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    start_reassurance(service, game_id)
    act(service, game_id, "前往新栖公寓", "travel")
    act(service, game_id, "查看方笙住处", "inspect")
    condition_id = "fang_sheng:condition:reassured"
    condition = next(
        item for item in db.get_social_states(game_id) if item["state_id"] == condition_id
    )
    assert condition["status"] == "active"
    assert condition["expires_at"] == 4

    act(service, game_id, "要求查看项目导出", "export")
    condition = next(
        item for item in db.get_social_states(game_id) if item["state_id"] == condition_id
    )
    assert condition["status"] == "ended"
    assert condition["ended_event_id"] is not None
    assert any(
        item["kind"] == "condition" and item["structured"].get("after", {}).get("status") == "ended"
        for item in db.get_character_history(game_id, include_private=True)
    )


def test_player_api_hides_private_trust_and_exposes_visible_history(tmp_path):
    """玩家接口只能看到公开或玩家履历，不能读取方笙的精确私密信任。"""
    client = TestClient(create_app(tmp_path / "api.db", model=SimulatedModel()))
    service = client.app.state.service
    game_id = client.post("/api/games", json={"protagonist": "江逢"}).json()["id"]
    start_reassurance(service, game_id)

    history_response = client.get(f"/api/games/{game_id}/character-history")
    assert history_response.status_code == 200
    items = history_response.json()["items"]
    assert items
    assert all(item["visibility"] in {"public", "player"} for item in items)
    assert all(item["kind"] != "trust" for item in items)
    assert "trust" not in client.get(f"/api/games/{game_id}").text


def test_preview_zero_time_chat_and_idempotent_replay_do_not_advance(tmp_path):
    """预览、零耗时交谈及重复请求不得推进游戏时间或局部模拟。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    start_reassurance(service, game_id)
    before = service.get_game(game_id)

    preview = service.preview_action(game_id, "前往新栖公寓", "travel_hc07")
    assert preview["mechanical_changes"][0]["world_time"] == {
        "before": 1, "after": 2, "time_cost": 1,
    }
    assert service.get_game(game_id) == before
    first = act(service, game_id, "询问委托细节", "details")
    second = act(service, game_id, "询问委托细节", "details")
    assert first == second
    assert db.get_case_state(game_id)["world_time"] == 1
    assert db.get_local_plans(game_id)[0]["status"] == "pending"


def test_hypothesis_crud_does_not_advance_local_simulation(tmp_path):
    """假设编辑不是世界行动，不得触发时间或计划变化。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    start_reassurance(service, game_id)
    hypothesis = service.create_hypothesis(game_id, "方笙还有补充")
    service.update_hypothesis(game_id, hypothesis["id"], "方笙会提供排班备注")
    service.delete_hypothesis(game_id, hypothesis["id"])

    assert db.get_case_state(game_id)["world_time"] == 1
    assert db.get_local_plans(game_id)[0]["status"] == "pending"


def test_invalid_social_change_rolls_back_action_and_all_projections(tmp_path):
    """信任越界时必须回滚行动、事件、案件时间和社会投影。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    next_state = {
        "phase": "unoffered", "location": "OC-01", "clock": 0,
        "world_time": 1, "clues": [], "ending": None,
    }
    changes = {
        "facts_add": [], "clock": None, "knowledge": [],
        "social": {
            "states": [{
                "state_id": "fang_sheng:player:trust", "holder_id": "fang_sheng",
                "target_id": "player", "kind": "trust", "value_int": 3,
                "value_text": None, "visibility": "private", "starts_at": 1,
                "expires_at": None, "status": "active",
            }],
            "history": [], "plans": [],
        },
    }

    with pytest.raises(ValueError, match="信任"):
        db.commit_action(
            game_id, "bad-trust", "非法信任", {"kind": "improvise"}, None,
            next_state, structured_changes=changes,
        )
    assert db.get_audit(game_id) == []
    assert len(db.get_events(game_id)) == 1
    assert db.get_case_state(game_id)["world_time"] == 0
    assert db.get_social_states(game_id) == []


def test_history_write_failure_rolls_back_social_state_and_action(tmp_path):
    """同源履历写入失败时不得留下孤立社会状态或已提交行动。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    changes = {
        "facts_add": [], "clock": None, "knowledge": [],
        "social": {
            "states": [{
                "state_id": "fang_sheng:player:relationship", "holder_id": "fang_sheng",
                "target_id": "player", "kind": "relationship", "value_int": None,
                "value_text": "委托人", "visibility": "public", "starts_at": 0,
                "expires_at": None, "status": "active",
            }],
            "history": [{
                "holder_id": "fang_sheng", "kind": "unknown", "content": "非法履历",
                "structured": {}, "visibility": "public",
            }],
            "plans": [],
        },
    }

    with pytest.raises(ValueError, match="履历"):
        db.commit_action(
            game_id, "bad-history", "非法履历", {"kind": "improvise"}, None,
            structured_changes=changes,
        )
    assert db.get_audit(game_id) == []
    assert len(db.get_events(game_id)) == 1
    assert db.get_social_states(game_id) == []
    assert db.get_character_history(game_id, include_private=True) == []


def test_v3_migration_backfills_only_public_commission_relationship(tmp_path):
    """v3 旧档只回填委托关系，保留备份，重复初始化不得新增记录。"""
    path = tmp_path / "v3.db"
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
                id INTEGER PRIMARY KEY AUTOINCREMENT, game_id TEXT NOT NULL REFERENCES games(id),
                action_id TEXT, kind TEXT NOT NULL, payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE case_states (
                game_id TEXT PRIMARY KEY REFERENCES games(id), phase TEXT NOT NULL,
                location TEXT NOT NULL, clock INTEGER NOT NULL DEFAULT 0,
                clues_json TEXT NOT NULL DEFAULT '[]', ending TEXT,
                revision INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE case_facts (
                game_id TEXT NOT NULL REFERENCES games(id), fact_id TEXT NOT NULL,
                subject_id TEXT NOT NULL, fact_kind TEXT NOT NULL,
                source_event_id INTEGER NOT NULL REFERENCES events(id),
                visibility TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('active', 'invalidated')),
                mechanical_json TEXT NOT NULL,
                invalidated_event_id INTEGER REFERENCES events(id),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(game_id, fact_id)
            );
            INSERT INTO games(id, protagonist, location, seed) VALUES ('g1', '江逢', 'OC-01', 1);
            INSERT INTO case_states(game_id, phase, location, clock, clues_json, revision)
            VALUES ('g1', 'active', 'OC-01', 0, '["commission"]', 2);
            INSERT INTO events(game_id, action_id, kind, payload_json)
            VALUES ('g1', NULL, 'legacy_v3_backfill', '{}');
            INSERT INTO case_facts(
                game_id, fact_id, subject_id, fact_kind, source_event_id,
                visibility, status, mechanical_json
            ) VALUES ('g1', 'commission', 'C01', 'clue', 1, 'player', 'active', '{}');
            PRAGMA user_version=3;
            """
        )

    db = Database(path).initialize()
    backup = tmp_path / "v3.db.pre-v4.bak"
    assert backup.exists()
    backup_bytes = backup.read_bytes()
    assert db.get_case_state("g1")["world_time"] == 0
    states = db.get_social_states("g1")
    assert len(states) == 1
    assert states[0]["kind"] == "relationship"
    history = db.get_character_history("g1", include_private=True)
    assert len(history) == 1
    assert history[0]["source_event_id"] == states[0]["source_event_id"]
    assert db.get_local_plans("g1") == []
    counts = (
        len(db.get_events("g1")), len(states), len(history),
    )

    Database(path).initialize()
    assert backup.read_bytes() == backup_bytes
    assert counts == (
        len(db.get_events("g1")), len(db.get_social_states("g1")),
        len(db.get_character_history("g1", include_private=True)),
    )
    assert sum(event["kind"] == "legacy_v4_backfill" for event in db.get_events("g1")) == 1
