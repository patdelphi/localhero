"""程序说明：验证 SQLite 初始化、事务回滚、事件顺序和幂等记录。"""

import sqlite3

import pytest

from app.store import Database


def test_database_uses_wal_and_foreign_keys(tmp_path):
    """数据库必须启用 WAL、外键，并保留 NORMAL 同步模式。"""
    db = Database(tmp_path / "game.db").initialize()
    with db.connect() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1


def test_create_and_load_game(tmp_path):
    """新存档应包含固定初始场景和开场事件。"""
    db = Database(tmp_path / "game.db").initialize()
    game = db.create_game("江逢")

    loaded = db.get_game(game["id"])
    events = db.get_events(game["id"])
    assert loaded["protagonist"] == "江逢"
    assert loaded["location"] == "OC-01"
    assert loaded["roll_count"] == 0
    assert events[0]["kind"] == "game_started"


def test_failed_transaction_does_not_leave_partial_event(tmp_path):
    """事务中的外键失败不得留下本事务已写入的事件。"""
    db = Database(tmp_path / "game.db").initialize()
    game = db.create_game("江逢")
    before = len(db.get_events(game["id"]))

    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO events(game_id, action_id, kind, payload_json) VALUES (?, NULL, ?, ?)",
                (game["id"], "valid_before_failure", "{}"),
            )
            conn.execute(
                "INSERT INTO events(game_id, action_id, kind, payload_json) VALUES (?, NULL, ?, ?)",
                ("missing-game", "invalid_game", "{}"),
            )

    assert len(db.get_events(game["id"])) == before


def test_action_request_id_is_unique_per_game(tmp_path):
    """同一游戏的请求标识必须唯一，防止重复提交事实。"""
    db = Database(tmp_path / "game.db").initialize()
    game = db.create_game("江逢")
    intent = {"kind": "inspect", "tendency": "洞察", "requires_roll": True, "modifier": 1}
    roll = {"dice": [4, 5], "modifier": 1, "total": 10, "outcome": "success"}
    db.commit_action(game["id"], "request-1", "查看现场", intent, roll)

    with pytest.raises(sqlite3.IntegrityError):
        db.commit_action(game["id"], "request-1", "查看现场", intent, roll)

    assert db.get_game(game["id"])["roll_count"] == 1
