"""程序说明：使用 SQLite 版本迁移和事务保存游戏、幂等行动、审计与事件。"""

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import uuid

from app.action_protocol import IdempotencyConflict, StateConflict


class Database:
    """封装存档读写；所有写入都在显式事务中完成。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        """建立带行工厂和外键约束的短连接，读取结束即关闭。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        """立即取得写锁；任一语句失败时回滚整个事务。"""
        with self.connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def initialize(self) -> "Database":
        """在事务中创建或迁移到版本 2，并启用 WAL。"""
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            has_game_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='games'"
            ).fetchone()
            action_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(actions)").fetchall()
            }
            case_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(case_states)").fetchall()
            }
        # 已有存档在首次升级到 v2 前备份；新建空库不制造无意义副本。
        if has_game_table and (
            version < 2
            or "request_hash" not in action_columns
            or "revision" not in case_columns
        ):
            self._backup_before_v2()
        schema = (
            """
            CREATE TABLE IF NOT EXISTS games (
                id TEXT PRIMARY KEY,
                protagonist TEXT NOT NULL,
                location TEXT NOT NULL,
                seed INTEGER NOT NULL,
                roll_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS actions (
                id TEXT PRIMARY KEY,
                game_id TEXT NOT NULL REFERENCES games(id),
                request_id TEXT NOT NULL,
                request_hash TEXT,
                input_text TEXT NOT NULL,
                command_json TEXT,
                intent_json TEXT NOT NULL,
                declaration_json TEXT,
                audit_json TEXT,
                roll_json TEXT,
                rules_version TEXT,
                content_version TEXT,
                status TEXT NOT NULL,
                response_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                UNIQUE(game_id, request_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL REFERENCES games(id),
                action_id TEXT REFERENCES actions(id),
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS case_states (
                game_id TEXT PRIMARY KEY REFERENCES games(id),
                phase TEXT NOT NULL,
                location TEXT NOT NULL,
                clock INTEGER NOT NULL DEFAULT 0,
                clues_json TEXT NOT NULL DEFAULT '[]',
                ending TEXT,
                revision INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
        )
        with self.transaction() as conn:
            for statement in schema:
                conn.execute(statement)
            self._migrate_columns(conn)
            conn.execute("PRAGMA user_version=2")
        return self

    def _backup_before_v2(self) -> None:
        """用 SQLite 在线备份保留迁移前一致性快照，绝不覆盖既有备份。"""
        backup_path = self.path.with_name(self.path.name + ".pre-v2.bak")
        if backup_path.exists():
            return
        temporary_path = self.path.with_name(
            f"{self.path.name}.{uuid.uuid4().hex}.backup-tmp"
        )
        with self.connect() as source:
            destination = sqlite3.connect(temporary_path)
            try:
                source.backup(destination)
            finally:
                destination.close()
        temporary_path.replace(backup_path)

    @staticmethod
    def _migrate_columns(conn: sqlite3.Connection) -> None:
        """只补可推导字段；旧行动明确保留 legacy 审计缺口。"""
        action_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(actions)").fetchall()
        }
        additions = {
            "request_hash": "TEXT",
            "command_json": "TEXT",
            "declaration_json": "TEXT",
            "audit_json": "TEXT",
            "rules_version": "TEXT",
            "content_version": "TEXT",
        }
        for name, sql_type in additions.items():
            if name not in action_columns:
                conn.execute(f"ALTER TABLE actions ADD COLUMN {name} {sql_type}")
        case_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(case_states)").fetchall()
        }
        if "revision" not in case_columns:
            conn.execute(
                "ALTER TABLE case_states ADD COLUMN revision INTEGER NOT NULL DEFAULT 0"
            )
        conn.execute(
            """
            UPDATE actions
            SET audit_json='{"audit_version":"legacy"}',
                rules_version='legacy', content_version='legacy'
            WHERE audit_json IS NULL
            """
        )

    def create_game(self, protagonist: str) -> dict:
        """创建固定于 OC-01 的新存档，并写入开场事件。"""
        game_id = uuid.uuid4().hex
        opening = "雨敲着事务所的旧窗。唐葵坐在案件板旁，桌上的终端还亮着。你可以查看现场、检查终端，或和她谈谈。"
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO games(id, protagonist, location, seed) VALUES (?, ?, ?, ?)",
                (game_id, protagonist, "OC-01", 20261103),
            )
            conn.execute(
                "INSERT INTO events(game_id, action_id, kind, payload_json) VALUES (?, NULL, ?, ?)",
                (game_id, "game_started", json.dumps({"text": opening}, ensure_ascii=False)),
            )
            conn.execute(
                """
                INSERT INTO case_states(game_id, phase, location, clock, clues_json, ending, revision)
                VALUES (?, 'unoffered', 'OC-01', 0, '[]', NULL, 0)
                """,
                (game_id,),
            )
        return self.get_game(game_id)

    def get_game(self, game_id: str) -> dict:
        """读取唯一存档，不存在时由调用层转换为 404。"""
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
        if row is None:
            raise KeyError("存档不存在")
        return dict(row)

    def get_case_state(self, game_id: str) -> dict:
        """读取案件状态；旧存档若无状态行则返回 C01 初始状态。"""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM case_states WHERE game_id=?", (game_id,)
            ).fetchone()
        if row is None:
            from app.case_engine import initial_state

            return initial_state()
        data = dict(row)
        data["clues"] = json.loads(data.pop("clues_json"))
        return data

    def get_events(self, game_id: str) -> list[dict]:
        """按实际提交顺序返回事件及结构化载荷。"""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE game_id=? ORDER BY id", (game_id,)
            ).fetchall()
        return [
            {**dict(row), "payload": json.loads(row["payload_json"])}
            for row in rows
        ]

    def commit_action(
        self,
        game_id: str,
        request_id: str,
        input_text: str,
        intent: dict,
        roll: dict | None,
        case_state: dict | None = None,
        *,
        request_hash: str | None = None,
        expected_revision: int | None = None,
        expected_roll_count: int | None = None,
        command: dict | None = None,
        declaration: dict | None = None,
        audit: dict | None = None,
    ) -> dict:
        """事务内复核幂等、状态版本和随机序号，再提交行动及案件事实。"""
        action_id = uuid.uuid4().hex
        with self.transaction() as conn:
            if request_hash is not None:
                existing = conn.execute(
                    "SELECT * FROM actions WHERE game_id=? AND request_id=?",
                    (game_id, request_id),
                ).fetchone()
                if existing:
                    if existing["request_hash"] != request_hash:
                        raise IdempotencyConflict("请求标识已用于不同命令")
                    action_id = existing["id"]
                    return self._decode_action(existing)

            game = conn.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
            if game is None:
                raise KeyError("存档不存在")
            current_case = conn.execute(
                "SELECT * FROM case_states WHERE game_id=?", (game_id,)
            ).fetchone()
            current_revision = current_case["revision"] if current_case else 0
            if expected_revision is not None and current_revision != expected_revision:
                raise StateConflict("案件状态已变化，请重新预览")
            if expected_roll_count is not None and game["roll_count"] != expected_roll_count:
                raise StateConflict("随机序号已变化，请重新预览")

            conn.execute(
                """
                INSERT INTO actions(
                    id, game_id, request_id, request_hash, input_text, command_json,
                    intent_json, declaration_json, audit_json, roll_json,
                    rules_version, content_version, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'narrative_pending')
                """,
                (
                    action_id,
                    game_id,
                    request_id,
                    request_hash,
                    input_text,
                    json.dumps(command, ensure_ascii=False) if command else None,
                    json.dumps(intent, ensure_ascii=False),
                    json.dumps(declaration, ensure_ascii=False) if declaration else None,
                    json.dumps(audit, ensure_ascii=False) if audit else None,
                    json.dumps(roll, ensure_ascii=False) if roll else None,
                    audit.get("rules_version") if audit else None,
                    audit.get("content_version") if audit else None,
                ),
            )
            if roll:
                conn.execute(
                    "UPDATE games SET roll_count=? WHERE id=?",
                    (game["roll_count"] + 1, game_id),
                )
            conn.execute(
                "INSERT INTO events(game_id, action_id, kind, payload_json) VALUES (?, ?, ?, ?)",
                (
                    game_id,
                    action_id,
                    "action_committed",
                    json.dumps(
                        {"input": input_text, "intent": intent, "roll": roll},
                        ensure_ascii=False,
                    ),
                ),
            )
            if case_state:
                next_revision = current_revision + 1
                conn.execute(
                    "UPDATE games SET location=? WHERE id=?",
                    (case_state["location"], game_id),
                )
                conn.execute(
                    """
                    INSERT INTO case_states(
                        game_id, phase, location, clock, clues_json, ending, revision
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(game_id) DO UPDATE SET
                        phase=excluded.phase,
                        location=excluded.location,
                        clock=excluded.clock,
                        clues_json=excluded.clues_json,
                        ending=excluded.ending,
                        revision=excluded.revision,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (
                        game_id,
                        case_state["phase"],
                        case_state["location"],
                        case_state["clock"],
                        json.dumps(case_state["clues"], ensure_ascii=False),
                        case_state["ending"],
                        next_revision,
                    ),
                )
                conn.execute(
                    "INSERT INTO events(game_id, action_id, kind, payload_json) VALUES (?, ?, ?, ?)",
                    (
                        game_id,
                        action_id,
                        "case_changed",
                        json.dumps(
                            {
                                "phase": case_state["phase"],
                                "location": case_state["location"],
                                "clock": case_state["clock"],
                                "clues": list(case_state["clues"]),
                                "ending": case_state["ending"],
                                "revision": next_revision,
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )
        return self.get_action(game_id, action_id)

    def get_action(self, game_id: str, action_id: str) -> dict:
        """读取行动并反序列化已保存的协议、判定、审计和响应。"""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM actions WHERE id=? AND game_id=?", (action_id, game_id)
            ).fetchone()
        if row is None:
            raise KeyError("行动不存在")
        return self._decode_action(row)

    def get_action_by_request(self, game_id: str, request_id: str) -> dict | None:
        """查询幂等请求是否已经存在。"""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM actions WHERE game_id=? AND request_id=?",
                (game_id, request_id),
            ).fetchone()
        return self._decode_action(row) if row else None

    def get_audit(self, game_id: str, limit: int = 50) -> list[dict]:
        """返回有界只读审计及其关联事件，不生成第二份事实权威。"""
        bounded_limit = max(1, min(int(limit), 100))
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM actions WHERE game_id=? ORDER BY rowid DESC LIMIT ?",
                (game_id, bounded_limit),
            ).fetchall()
            event_rows = conn.execute(
                """
                SELECT id, action_id, kind, created_at FROM events
                WHERE game_id=? AND action_id IS NOT NULL ORDER BY id
                """,
                (game_id,),
            ).fetchall()
        events_by_action = {}
        for event in event_rows:
            events_by_action.setdefault(event["action_id"], []).append(dict(event))
        result = []
        for row in rows:
            action = self._decode_action(row)
            result.append(
                {
                    "action_id": action["id"],
                    "request_id": action["request_id"],
                    "input_text": action["input_text"],
                    "intent": action["intent"],
                    "declaration": action["declaration"],
                    "roll": action["roll"],
                    "status": action["status"],
                    "created_at": action["created_at"],
                    "audit": action["audit"],
                    "events": events_by_action.get(action["id"], []),
                }
            )
        return result

    def complete_action(self, game_id: str, action_id: str, narrative: str) -> dict:
        """条件更新待叙事行动；并发下只有成功更新者追加完成事件。"""
        action = self.get_action(game_id, action_id)
        if action["status"] == "complete":
            return json.loads(action["response_json"])

        response = self._pending_response(action)
        response.update({"status": "complete", "narrative": narrative})
        audit = action["audit"]
        if audit.get("audit_version") == 1:
            audit = {**audit, "status": "complete"}
        with self.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE actions
                SET status='complete', response_json=?, audit_json=?,
                    completed_at=CURRENT_TIMESTAMP
                WHERE id=? AND game_id=? AND status='narrative_pending'
                """,
                (
                    json.dumps(response, ensure_ascii=False),
                    json.dumps(audit, ensure_ascii=False),
                    action_id,
                    game_id,
                ),
            )
            if cursor.rowcount == 1:
                conn.execute(
                    "INSERT INTO events(game_id, action_id, kind, payload_json) VALUES (?, ?, ?, ?)",
                    (
                        game_id,
                        action_id,
                        "narrative_completed",
                        json.dumps({"text": narrative}, ensure_ascii=False),
                    ),
                )
        current = self.get_action(game_id, action_id)
        if current["status"] == "complete":
            return json.loads(current["response_json"])
        return self._pending_response(current)

    @staticmethod
    def _decode_action(row: sqlite3.Row) -> dict:
        """统一处理可空 JSON 字段和旧数据审计缺口。"""
        result = dict(row)
        result["intent"] = json.loads(result["intent_json"])
        result["roll"] = json.loads(result["roll_json"]) if result["roll_json"] else None
        for column, key in (
            ("command_json", "command"),
            ("declaration_json", "declaration"),
            ("audit_json", "audit"),
        ):
            result[key] = json.loads(result[column]) if result.get(column) else None
        if result["audit"] is None:
            result["audit"] = {"audit_version": "legacy"}
        return result

    @staticmethod
    def _pending_response(action: dict) -> dict:
        """构造事实已提交但叙事未完成的可恢复响应。"""
        return {
            "status": "narrative_pending",
            "action_id": action["id"],
            "game_id": action["game_id"],
            "request_id": action["request_id"],
            "intent": action["intent"],
            "declaration": action.get("declaration"),
            "roll": action["roll"],
            "narrative": None,
        }
