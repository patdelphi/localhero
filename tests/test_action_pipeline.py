"""程序说明：验证通用行动管线、预览、权限、状态冲突、迁移和完整审计。"""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.action_pipeline import CaseAuthorizer
from app.action_protocol import IdempotencyConflict, PermissionDenied, StateConflict
from app.game import GameService
from app.main import create_app
from app.model import SimulatedModel
from app.store import Database


def make_service(tmp_path):
    """建立只使用临时存档的服务。"""
    db = Database(tmp_path / "game.db").initialize()
    return GameService(db, SimulatedModel()), db


def test_preview_has_declaration_and_no_side_effects(tmp_path):
    """预览必须展示掷骰前信息，且不写事件、不消耗随机序号。"""
    service, db = make_service(tmp_path)
    game = service.create_game("江逢")

    preview = service.preview_action(
        game["id"], "接受方笙的委托", action_id="accept_commission"
    )

    assert preview["can_submit"] is True
    assert preview["revision"] == 0
    assert preview["selected_action"]["action_id"] == "accept_commission"
    assert preview["declaration"]["target"]
    assert preview["declaration"]["position"]
    assert preview["declaration"]["effect"]
    assert preview["declaration"]["cost"]
    assert preview["declaration"]["modifier_source"]
    assert preview["random"] is None
    assert [step["stage"] for step in preview["pipeline"]] == [
        "Before",
        "Instead",
        "Check",
        "After",
    ]
    assert db.get_game(game["id"])["roll_count"] == 0
    assert db.get_case_state(game["id"])["revision"] == 0
    assert len(db.get_events(game["id"])) == 1


def test_explicit_instead_cannot_bypass_check(tmp_path):
    """显式宿主命令只选择替代计划，不能跳过合法性检查。"""
    service, db = make_service(tmp_path)
    game = service.create_game("江逢")

    preview = service.preview_action(
        game["id"], "前往新栖公寓", action_id="travel_hc07"
    )
    assert preview["can_submit"] is False
    assert preview["reason"]

    with pytest.raises(PermissionDenied):
        service.act(
            game["id"],
            "前往新栖公寓",
            "illegal-1",
            action_id="travel_hc07",
        )

    assert len(db.get_events(game["id"])) == 1
    assert db.get_game(game["id"])["roll_count"] == 0


def test_expected_revision_conflict_rolls_back_everything(tmp_path):
    """状态版本冲突不得留下行动、事件或随机消耗。"""
    service, db = make_service(tmp_path)
    game = service.create_game("江逢")

    with pytest.raises(StateConflict):
        service.act(
            game["id"],
            "接受方笙的委托",
            "stale-1",
            action_id="accept_commission",
            expected_revision=1,
        )

    assert db.get_game(game["id"])["roll_count"] == 0
    assert db.get_case_state(game["id"])["revision"] == 0
    assert len(db.get_events(game["id"])) == 1
    assert db.get_audit(game["id"]) == []


def test_request_id_reuse_with_different_hash_is_conflict(tmp_path):
    """同一请求标识不能承载不同命令内容。"""
    service, db = make_service(tmp_path)
    game = service.create_game("江逢")
    service.act(game["id"], "接受方笙的委托", "same-request")

    with pytest.raises(IdempotencyConflict):
        service.act(game["id"], "拒绝委托", "same-request")

    assert len(db.get_audit(game["id"])) == 1
    # 开场、行动、案件变化、社会变化、叙事各一条；冲突请求没有新增事件。
    assert len(db.get_events(game["id"])) == 5


def test_committed_action_has_complete_trace_and_event_links(tmp_path):
    """审计应保留候选、排除、管线、权限、随机、版本和事件关联。"""
    service, db = make_service(tmp_path)
    game = service.create_game("江逢")
    result = service.act(game["id"], "检查终端", "audit-1")

    entries = db.get_audit(game["id"])
    assert len(entries) == 1
    entry = entries[0]
    audit = entry["audit"]
    assert entry["action_id"] == result["action_id"]
    assert audit["audit_version"] == 1
    assert audit["rules_version"]
    assert audit["content_version"]
    assert audit["candidates"]
    assert any(not item["eligible"] for item in audit["candidates"])
    assert audit["selected_action"]["selection_source"] == "parsed_intent"
    assert audit["permission"]["allowed"] is True
    assert audit["random"]["sequence"] == 0
    assert audit["random"]["dice"] == result["roll"]["dice"]
    assert audit["state_revision"] == {"before": 0, "after": 0}
    assert {event["kind"] for event in entry["events"]} == {
        "action_committed",
        "narrative_completed",
    }


def test_case_authorizer_rejects_global_canon_write():
    """案件权限与全球正典权限不能混用。"""
    with pytest.raises(PermissionDenied):
        CaseAuthorizer().authorize(
            {"scope": "global_canon", "object": "city", "effect": "rewrite"}
        )


def test_legacy_database_migrates_with_explicit_audit_gap(tmp_path):
    """旧存档升级到当前版本，历史行动只标记 legacy，不伪造轨迹。"""
    path = tmp_path / "legacy.db"
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
                request_id TEXT NOT NULL, input_text TEXT NOT NULL,
                intent_json TEXT NOT NULL, roll_json TEXT, status TEXT NOT NULL,
                response_json TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT, UNIQUE(game_id, request_id)
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
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO games(id, protagonist, location, seed) VALUES ('g1', '江逢', 'OC-01', 1);
            INSERT INTO case_states(game_id, phase, location) VALUES ('g1', 'unoffered', 'OC-01');
            INSERT INTO actions(id, game_id, request_id, input_text, intent_json, status)
            VALUES ('a1', 'g1', 'r1', '旧行动', '{"kind":"improvise"}', 'narrative_pending');
            """
        )

    db = Database(path).initialize()
    backup_path = tmp_path / "legacy.db.pre-v2.bak"
    assert backup_path.exists(), "实际旧存档迁移前必须保留一致性备份"
    with sqlite3.connect(backup_path) as backup:
        old_columns = {
            row[1] for row in backup.execute("PRAGMA table_info(actions)").fetchall()
        }
        assert "request_hash" not in old_columns
        assert backup.execute("SELECT COUNT(*) FROM actions").fetchone()[0] == 1
    assert (tmp_path / "legacy.db.pre-v3.bak").exists()
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(actions)").fetchall()
        }
    assert {"request_hash", "command_json", "declaration_json", "audit_json"} <= columns
    assert db.get_case_state("g1")["revision"] == 0
    assert db.get_audit("g1")[0]["audit"]["audit_version"] == "legacy"


def test_preview_and_audit_http_api(tmp_path):
    """HTTP 层应暴露只读预览、版本状态和审计列表。"""
    client = TestClient(create_app(tmp_path / "api.db", model=SimulatedModel()))
    game_id = client.post("/api/games", json={"protagonist": "江逢"}).json()["id"]

    preview = client.post(
        f"/api/games/{game_id}/actions/preview",
        json={"text": "接受方笙的委托", "action_id": "accept_commission"},
    )
    assert preview.status_code == 200
    assert preview.json()["declaration"]["position"]

    acted = client.post(
        f"/api/games/{game_id}/actions",
        json={
            "text": "接受方笙的委托",
            "request_id": "api-action-1",
            "action_id": "accept_commission",
            "expected_revision": preview.json()["revision"],
        },
    )
    assert acted.status_code == 200
    assert acted.json()["case"]["revision"] == 1

    audit = client.get(f"/api/games/{game_id}/audit?limit=10")
    assert audit.status_code == 200
    assert audit.json()["items"][0]["audit"]["selected_action"]["action_id"] == (
        "accept_commission"
    )

    stale = client.post(
        f"/api/games/{game_id}/actions",
        json={
            "text": "拒绝委托",
            "request_id": "api-action-2",
            "expected_revision": 0,
        },
    )
    assert stale.status_code == 409


def test_stale_preview_returns_conflict_before_revalidation(tmp_path):
    """另一标签已执行相同行动时，过期预览仍应返回 409 而非权限错误。"""
    client = TestClient(create_app(tmp_path / "stale-preview.db", model=SimulatedModel()))
    game_id = client.post("/api/games", json={"protagonist": "江逢"}).json()["id"]
    accepted = client.post(
        f"/api/games/{game_id}/actions",
        json={"text": "接受方笙的委托", "request_id": "accept", "expected_revision": 0},
    )
    assert accepted.status_code == 200
    preview = client.post(
        f"/api/games/{game_id}/actions/preview",
        json={"text": "前往新栖公寓", "action_id": "travel_hc07"},
    ).json()

    command = {
        "text": "前往新栖公寓",
        "action_id": "travel_hc07",
        "expected_revision": preview["revision"],
    }
    first = client.post(
        f"/api/games/{game_id}/actions",
        json={**command, "request_id": "first-tab"},
    )
    stale = client.post(
        f"/api/games/{game_id}/actions",
        json={**command, "request_id": "stale-tab"},
    )

    assert first.status_code == 200
    assert stale.status_code == 409
    assert "状态" in stale.json()["detail"]
    assert len(client.get(f"/api/games/{game_id}").json()["events"]) == 8
    assert len(client.get(f"/api/games/{game_id}/audit").json()["items"]) == 2


def test_roll_sequence_conflict_does_not_consume_or_write(tmp_path):
    """即使状态版本相同，随机序号过期也必须拒绝整个提交。"""
    service, db = make_service(tmp_path)
    game = service.create_game("江逢")
    intent = {"kind": "inspect", "tendency": "洞察", "requires_roll": True, "modifier": 1}
    roll = {"dice": [4, 5], "modifier": 1, "total": 10, "outcome": "success"}

    with pytest.raises(StateConflict):
        db.commit_action(
            game["id"],
            "stale-roll",
            "检查终端",
            intent,
            roll,
            request_hash="stale-roll-hash",
            expected_revision=0,
            expected_roll_count=1,
        )

    assert db.get_game(game["id"])["roll_count"] == 0
    assert len(db.get_events(game["id"])) == 1
    assert db.get_audit(game["id"]) == []


def test_action_write_failure_rolls_back_action_and_event(tmp_path):
    """主行动后的案件序列化失败也不能留下部分行动。"""
    service, db = make_service(tmp_path)
    game = service.create_game("江逢")
    intent = {"kind": "case_action", "action_id": "accept_commission"}
    invalid_case = {
        "phase": "active",
        "location": "OC-01",
        "clock": 0,
        "clues": {"不可序列化集合"},
        "ending": None,
    }

    with pytest.raises(TypeError):
        db.commit_action(game["id"], "broken-write", "接受委托", intent, None, invalid_case)

    assert db.get_audit(game["id"]) == []
    assert len(db.get_events(game["id"])) == 1
    assert db.get_case_state(game["id"])["phase"] == "unoffered"


def test_concurrent_narrative_completion_appends_one_event(tmp_path):
    """并发叙事完成只能有一个条件更新成功者追加事件。"""
    db = Database(tmp_path / "game.db").initialize()
    service = GameService(db, SimulatedModel(fail_narrative_times=1))
    game = service.create_game("江逢")
    pending = service.act(game["id"], "检查终端", "narrative-race")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: db.complete_action(
                    game["id"], pending["action_id"], "已提交事实的叙事"
                ),
                range(2),
            )
        )

    assert all(result["status"] == "complete" for result in results)
    kinds = [event["kind"] for event in db.get_events(game["id"])]
    assert kinds.count("narrative_completed") == 1
