"""程序说明：使用 SQLite 版本迁移和事务保存游戏、幂等行动、审计与事件。"""

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import uuid

from app.action_protocol import IdempotencyConflict, RULES_VERSION, StateConflict
from app.case_content import CONTENT_VERSION
from app.city_schedule import build_offscreen_payload


class Database:
    """封装存档读写；所有写入都在显式事务中完成。"""

    def __init__(self, path: str | Path):
        # 命名内存 URI 供隔离回放使用；普通存档仍统一转换为 Path。
        self.uri = isinstance(path, str) and path.startswith("file:")
        self.path = path if self.uri else Path(path)

    @contextmanager
    def connect(self):
        """建立带行工厂和外键约束的短连接，读取结束即关闭。"""
        if not self.uri:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30, uri=self.uri)
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
        """在事务中创建或迁移到版本 7，并启用 WAL。"""
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
        # 每次跨版本升级都保留独立快照；已有备份绝不覆盖。
        if has_game_table and (
            version < 2
            or "request_hash" not in action_columns
            or "revision" not in case_columns
        ):
            self._backup_before_v2()
        needs_v3_backfill = bool(has_game_table and version < 3)
        if needs_v3_backfill:
            self._backup_before_v3()
        needs_v4_backfill = bool(has_game_table and version < 4)
        if needs_v4_backfill:
            self._backup_before_v4()
        if has_game_table and version < 5:
            self._backup_before_v5()
        if has_game_table and version < 6:
            self._backup_before_v6()
        if has_game_table and version < 7:
            self._backup_before_v7()
        if has_game_table and version < 8:
            self._backup_before_v8()
        schema = (
            """
            CREATE TABLE IF NOT EXISTS games (
                id TEXT PRIMARY KEY,
                protagonist TEXT NOT NULL,
                location TEXT NOT NULL,
                seed INTEGER NOT NULL,
                roll_count INTEGER NOT NULL DEFAULT 0,
                case_id TEXT NOT NULL DEFAULT 'C01',
                parent_game_id TEXT REFERENCES games(id),
                fork_action_id TEXT,
                fork_action_index INTEGER,
                branch_label TEXT,
                branch_status TEXT NOT NULL DEFAULT 'active',
                branch_created_at TEXT,
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
                world_time INTEGER NOT NULL DEFAULT 0,
                clues_json TEXT NOT NULL DEFAULT '[]',
                ending TEXT,
                revision INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS case_facts (
                game_id TEXT NOT NULL REFERENCES games(id),
                fact_id TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                fact_kind TEXT NOT NULL,
                source_event_id INTEGER NOT NULL REFERENCES events(id),
                visibility TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('active', 'invalidated')),
                mechanical_json TEXT NOT NULL,
                invalidated_event_id INTEGER REFERENCES events(id),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(game_id, fact_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS clock_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL REFERENCES games(id),
                clock_id TEXT NOT NULL,
                source_event_id INTEGER NOT NULL REFERENCES events(id),
                reason TEXT NOT NULL,
                delta INTEGER NOT NULL,
                before_value INTEGER NOT NULL,
                after_value INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(game_id, clock_id, source_event_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS knowledge_records (
                id TEXT PRIMARY KEY,
                game_id TEXT NOT NULL REFERENCES games(id),
                holder_id TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('observation', 'memory', 'testimony')),
                source_event_id INTEGER NOT NULL REFERENCES events(id),
                fact_id TEXT,
                content TEXT NOT NULL,
                accuracy TEXT NOT NULL,
                visibility TEXT NOT NULL,
                source_record_id TEXT REFERENCES knowledge_records(id),
                observed_at INTEGER,
                precision TEXT NOT NULL DEFAULT 'unknown'
                    CHECK(precision IN ('exact', 'vague', 'fragmentary', 'unknown')),
                corrects_record_id TEXT REFERENCES knowledge_records(id),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(game_id, fact_id) REFERENCES case_facts(game_id, fact_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS social_states (
                game_id TEXT NOT NULL REFERENCES games(id),
                state_id TEXT NOT NULL,
                holder_id TEXT NOT NULL,
                target_id TEXT,
                kind TEXT NOT NULL CHECK(kind IN ('relationship', 'trust', 'condition')),
                value_int INTEGER,
                value_text TEXT,
                visibility TEXT NOT NULL CHECK(visibility IN ('public', 'player', 'private')),
                starts_at INTEGER NOT NULL,
                expires_at INTEGER,
                status TEXT NOT NULL CHECK(status IN ('active', 'ended')),
                source_event_id INTEGER NOT NULL REFERENCES events(id),
                ended_event_id INTEGER REFERENCES events(id),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(game_id, state_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS character_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL REFERENCES games(id),
                holder_id TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('relationship', 'trust', 'condition', 'social_memory', 'plan')),
                content TEXT NOT NULL,
                structured_json TEXT NOT NULL,
                visibility TEXT NOT NULL CHECK(visibility IN ('public', 'player', 'private')),
                source_event_id INTEGER NOT NULL REFERENCES events(id),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS local_plans (
                game_id TEXT NOT NULL REFERENCES games(id),
                plan_id TEXT NOT NULL,
                holder_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                due_time INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending', 'completed')),
                source_event_id INTEGER NOT NULL REFERENCES events(id),
                completed_event_id INTEGER REFERENCES events(id),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(game_id, plan_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS replay_baselines (
                game_id TEXT PRIMARY KEY REFERENCES games(id),
                snapshot_json TEXT NOT NULL,
                snapshot_format INTEGER NOT NULL,
                rules_version TEXT NOT NULL,
                content_version TEXT NOT NULL,
                snapshot_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS player_hypotheses (
                id TEXT PRIMARY KEY,
                game_id TEXT NOT NULL REFERENCES games(id),
                text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_case_facts_active ON case_facts(game_id, status)",
            "CREATE INDEX IF NOT EXISTS idx_clock_changes_game ON clock_changes(game_id, id)",
            "CREATE INDEX IF NOT EXISTS idx_knowledge_player ON knowledge_records(game_id, visibility, id)",
            "CREATE INDEX IF NOT EXISTS idx_social_states_game ON social_states(game_id, kind, status)",
            "CREATE INDEX IF NOT EXISTS idx_character_history_game ON character_history(game_id, visibility, source_event_id, id)",
            "CREATE INDEX IF NOT EXISTS idx_local_plans_due ON local_plans(game_id, status, due_time, plan_id)",
            "CREATE INDEX IF NOT EXISTS idx_hypotheses_game ON player_hypotheses(game_id, created_at)",
        )
        with self.transaction() as conn:
            for statement in schema:
                conn.execute(statement)
            self._migrate_columns(conn)
            # v5 旧表须先补齐 v6 列，再创建依赖这些列的索引。
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_knowledge_source_record "
                "ON knowledge_records(game_id, source_record_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_knowledge_corrects_record "
                "ON knowledge_records(game_id, corrects_record_id)"
            )
            if needs_v3_backfill:
                self._backfill_v3(conn)
            if needs_v4_backfill:
                self._backfill_v4(conn)
            conn.execute("PRAGMA user_version=8")
        return self

    def _backup_before_v2(self) -> None:
        """保留首次升级到 v2 前的一致性快照。"""
        self._backup("pre-v2")

    def _backup_before_v3(self) -> None:
        """保留首次升级到 v3 前的一致性快照。"""
        self._backup("pre-v3")

    def _backup_before_v4(self) -> None:
        """保留首次升级到 v4 前的一致性快照。"""
        self._backup("pre-v4")

    def _backup_before_v5(self) -> None:
        """保留首次升级到 v5 前的一致性快照。"""
        self._backup("pre-v5")

    def _backup_before_v6(self) -> None:
        """保留首次升级到 v6 前的一致性快照。"""
        self._backup("pre-v6")

    def _backup_before_v7(self) -> None:
        """保留首次升级到 v7 前的一致性快照。"""
        self._backup("pre-v7")

    def _backup_before_v8(self) -> None:
        """保留首次升级到 v8 前的一致性快照。"""
        self._backup("pre-v8")

    def _backup(self, label: str) -> None:
        """使用 SQLite 在线备份；临时文件完成后原子替换目标。"""
        backup_path = self.path.with_name(f"{self.path.name}.{label}.bak")
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
        if "world_time" not in case_columns:
            conn.execute(
                "ALTER TABLE case_states ADD COLUMN world_time INTEGER NOT NULL DEFAULT 0"
            )
        game_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(games)").fetchall()
        }
        if "case_id" not in game_columns:
            # v7 只补一列；旧档全部按 C01 继续运行。
            conn.execute(
                "ALTER TABLE games ADD COLUMN case_id TEXT NOT NULL DEFAULT 'C01'"
            )
        # v8 分支元数据：旧档作为根存档，分支状态默认 active。
        branch_additions = {
            "parent_game_id": "TEXT",
            "fork_action_id": "TEXT",
            "fork_action_index": "INTEGER",
            "branch_label": "TEXT",
            "branch_created_at": "TEXT",
        }
        for name, sql_type in branch_additions.items():
            if name not in game_columns:
                conn.execute(f"ALTER TABLE games ADD COLUMN {name} {sql_type}")
        if "branch_status" not in game_columns:
            conn.execute(
                "ALTER TABLE games ADD COLUMN branch_status TEXT NOT NULL DEFAULT 'active'"
            )
        knowledge_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(knowledge_records)").fetchall()
        }
        cognition_additions = {
            "source_record_id": "TEXT",
            "observed_at": "INTEGER",
            "precision": "TEXT NOT NULL DEFAULT 'unknown'",
            "corrects_record_id": "TEXT",
        }
        for name, sql_type in cognition_additions.items():
            if name not in knowledge_columns:
                conn.execute(f"ALTER TABLE knowledge_records ADD COLUMN {name} {sql_type}")
        conn.execute(
            """
            UPDATE actions
            SET audit_json='{"audit_version":"legacy"}',
                rules_version='legacy', content_version='legacy'
            WHERE audit_json IS NULL
            """
        )

    @staticmethod
    def _backfill_v3(conn: sqlite3.Connection) -> None:
        """只回填旧档当前快照，不伪造已经不可考的历史增减与感知过程。"""
        from app.case_content import CLUE_LABELS

        states = conn.execute("SELECT * FROM case_states ORDER BY game_id").fetchall()
        for state in states:
            game_id = state["game_id"]
            existing = conn.execute(
                "SELECT 1 FROM events WHERE game_id=? AND kind='legacy_v3_backfill'",
                (game_id,),
            ).fetchone()
            if existing:
                continue
            clues = json.loads(state["clues_json"])
            cursor = conn.execute(
                "INSERT INTO events(game_id, action_id, kind, payload_json) VALUES (?, NULL, ?, ?)",
                (
                    game_id,
                    "legacy_v3_backfill",
                    json.dumps(
                        {
                            "phase": state["phase"],
                            "location": state["location"],
                            "clock": state["clock"],
                            "clues": clues,
                            "ending": state["ending"],
                            "revision": state["revision"],
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            source_event_id = cursor.lastrowid
            for clue in clues:
                conn.execute(
                    """
                    INSERT INTO case_facts(
                        game_id, fact_id, subject_id, fact_kind, source_event_id,
                        visibility, status, mechanical_json
                    ) VALUES (?, ?, 'C01', 'clue', ?, 'player', 'active', ?)
                    """,
                    (
                        game_id,
                        clue,
                        source_event_id,
                        json.dumps(
                            {"legacy_snapshot": True, "grants_action_permission": True},
                            ensure_ascii=False,
                        ),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO knowledge_records(
                        id, game_id, holder_id, kind, source_event_id,
                        fact_id, content, accuracy, visibility
                    ) VALUES (?, ?, 'player', 'memory', ?, ?, ?, 'unknown', 'player')
                    """,
                    (
                        uuid.uuid4().hex,
                        game_id,
                        source_event_id,
                        clue,
                        f"迁移时已知：{CLUE_LABELS.get(clue, clue)}",
                    ),
                )
            conn.execute(
                """
                INSERT INTO clock_changes(
                    game_id, clock_id, source_event_id, reason,
                    delta, before_value, after_value
                ) VALUES (?, 'project_cleanup', ?, 'v2 到 v3 迁移时快照值', 0, ?, ?)
                """,
                (game_id, source_event_id, state["clock"], state["clock"]),
            )

    @staticmethod
    def _backfill_v4(conn: sqlite3.Connection) -> None:
        """旧档仅从有效委托事实回填公开关系，不伪造其他社会历史。"""
        commissions = conn.execute(
            """
            SELECT game_id FROM case_facts
            WHERE fact_id='commission' AND status='active' ORDER BY game_id
            """
        ).fetchall()
        for commission in commissions:
            game_id = commission["game_id"]
            existing = conn.execute(
                "SELECT 1 FROM events WHERE game_id=? AND kind='legacy_v4_backfill'",
                (game_id,),
            ).fetchone()
            if existing:
                continue
            cursor = conn.execute(
                "INSERT INTO events(game_id, action_id, kind, payload_json) VALUES (?, NULL, ?, ?)",
                (
                    game_id,
                    "legacy_v4_backfill",
                    json.dumps(
                        {"world_time": 0, "relationship": "方笙是玩家的委托人"},
                        ensure_ascii=False,
                    ),
                ),
            )
            event_id = cursor.lastrowid
            state_id = "fang_sheng:player:relationship"
            conn.execute(
                """
                INSERT INTO social_states(
                    game_id, state_id, holder_id, target_id, kind,
                    value_int, value_text, visibility, starts_at, expires_at,
                    status, source_event_id
                ) VALUES (?, ?, 'fang_sheng', 'player', 'relationship',
                          NULL, '委托人', 'public', 0, NULL, 'active', ?)
                """,
                (game_id, state_id, event_id),
            )
            conn.execute(
                """
                INSERT INTO character_history(
                    game_id, holder_id, kind, content, structured_json,
                    visibility, source_event_id
                ) VALUES (?, 'fang_sheng', 'relationship', '方笙成为你的委托人。',
                          ?, 'public', ?)
                """,
                (
                    game_id,
                    json.dumps(
                        {
                            "state_id": state_id,
                            "before": None,
                            "after": {"value_text": "委托人", "status": "active"},
                            "legacy_backfill": True,
                        },
                        ensure_ascii=False,
                    ),
                    event_id,
                ),
            )

    def create_game(self, protagonist: str, case=None) -> dict:
        """按案件创建新档，并在同一事务写入开场、案件投影与回放基线。"""
        # 延迟导入避免存储模块与回放模块在加载时形成循环依赖。
        from app.case_registry import default_case
        from app.replay_engine import canonical_json, make_initial_snapshot, snapshot_hash

        bundle = case or default_case()
        game_id = uuid.uuid4().hex
        snapshot_json = canonical_json(make_initial_snapshot(protagonist, bundle))
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO games(id, protagonist, location, seed, case_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (game_id, protagonist, bundle.start_location, 20261103, bundle.case_id),
            )
            cursor = conn.execute(
                "INSERT INTO events(game_id, action_id, kind, payload_json) VALUES (?, NULL, ?, ?)",
                (
                    game_id,
                    "game_started",
                    json.dumps(
                        {"text": bundle.opening, "case_id": bundle.case_id},
                        ensure_ascii=False,
                    ),
                ),
            )
            for record in bundle.initial_cognition(game_id, cursor.lastrowid):
                self._insert_knowledge_record(
                    conn, game_id, cursor.lastrowid, record
                )
            conn.execute(
                """
                INSERT INTO case_states(game_id, phase, location, clock, clues_json, ending, revision)
                VALUES (?, ?, ?, 0, '[]', NULL, 0)
                """,
                (game_id, bundle.start_phase, bundle.start_location),
            )
            conn.execute(
                """
                INSERT INTO replay_baselines(
                    game_id, snapshot_json, snapshot_format,
                    rules_version, content_version, snapshot_hash
                ) VALUES (?, ?, 1, ?, ?, ?)
                """,
                (
                    game_id, snapshot_json, RULES_VERSION, bundle.content_version,
                    snapshot_hash(snapshot_json),
                ),
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

    def count_actions(self, game_id: str) -> int:
        """返回存档已提交的行动条数，作为城市时段推进的节拍。"""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM actions WHERE game_id=?", (game_id,)
            ).fetchone()
        return int(row["total"])

    def get_case_facts(self, game_id: str) -> list[dict]:
        """读取事实及来源事件类型；失效历史仍保留。"""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT f.*, e.kind AS source_kind
                FROM case_facts f JOIN events e ON e.id=f.source_event_id
                WHERE f.game_id=? ORDER BY f.rowid
                """,
                (game_id,),
            ).fetchall()
        return [
            {**dict(row), "mechanical": json.loads(row["mechanical_json"])}
            for row in rows
        ]

    def get_clock_changes(self, game_id: str) -> list[dict]:
        """按提交顺序读取 Clock 变化及来源事件。"""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT c.*, e.kind AS source_kind
                FROM clock_changes c JOIN events e ON e.id=c.source_event_id
                WHERE c.game_id=? ORDER BY c.id
                """,
                (game_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_player_knowledge(self, game_id: str) -> list[dict]:
        """返回玩家认知；只有来源和目标均公开时才保留对应引用。"""
        with self.connect() as conn:
            rows = [dict(row) for row in conn.execute(
                """
                SELECT * FROM knowledge_records
                WHERE game_id=? AND visibility='player'
                ORDER BY source_event_id, rowid
                """,
                (game_id,),
            ).fetchall()]
        visible_ids = {row["id"] for row in rows}
        result = []
        for row in rows:
            corrected_by = [
                item["id"] for item in rows
                if item.get("corrects_record_id") == row["id"]
            ]
            result.append({
                "knowledge_id": row["id"],
                "holder_id": row["holder_id"],
                "kind": row["kind"],
                "source_event_id": row["source_event_id"],
                "fact_id": row["fact_id"],
                "content": row["content"],
                "accuracy": row["accuracy"],
                "visibility": row["visibility"],
                "source_record_id": (
                    row["source_record_id"]
                    if row["source_record_id"] in visible_ids else None
                ),
                "observed_at": row["observed_at"],
                "precision": row["precision"],
                "corrects_record_id": (
                    row["corrects_record_id"]
                    if row["corrects_record_id"] in visible_ids else None
                ),
                "has_correction": bool(corrected_by),
                "corrected_by": corrected_by,
            })
        return result

    def get_social_states(self, game_id: str) -> list[dict]:
        """读取社会结构投影；私密字段仅供规则引擎内部使用。"""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM social_states WHERE game_id=? ORDER BY rowid",
                (game_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_character_history(
        self, game_id: str, include_private: bool = False
    ) -> list[dict]:
        """按来源事件读取履历；玩家接口默认排除私密记录。"""
        visibility_sql = "" if include_private else "AND visibility IN ('public', 'player')"
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM character_history
                WHERE game_id=? {visibility_sql}
                ORDER BY source_event_id, id
                """,
                (game_id,),
            ).fetchall()
        return [
            {**dict(row), "structured": json.loads(row["structured_json"])}
            for row in rows
        ]

    def get_local_plans(self, game_id: str) -> list[dict]:
        """按固定到期顺序读取局部计划当前投影。"""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM local_plans WHERE game_id=?
                ORDER BY due_time, plan_id
                """,
                (game_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_decision_context(self, game_id: str) -> dict:
        """在单次一致性读取中取得NPC决策和并发哈希所需的全部输入。"""
        with self.connect() as conn:
            return self._decision_context_from_conn(conn, game_id)

    @staticmethod
    def _decision_context_from_conn(conn: sqlite3.Connection, game_id: str) -> dict:
        """从事务内当前投影构造规范上下文，不读取玩家私人假设。"""
        from app.npc_decision import make_decision_context

        game = conn.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
        if game is None:
            raise KeyError("存档不存在")
        case_row = conn.execute(
            "SELECT * FROM case_states WHERE game_id=?", (game_id,)
        ).fetchone()
        if case_row is None:
            from app.case_engine import initial_state
            case = initial_state()
        else:
            case = dict(case_row)
            case["clues"] = json.loads(case.pop("clues_json"))
        social = [dict(row) for row in conn.execute(
            "SELECT * FROM social_states WHERE game_id=? ORDER BY rowid", (game_id,)
        ).fetchall()]
        plans = [dict(row) for row in conn.execute(
            "SELECT * FROM local_plans WHERE game_id=? ORDER BY due_time, plan_id",
            (game_id,),
        ).fetchall()]
        knowledge = [dict(row) for row in conn.execute(
            "SELECT * FROM knowledge_records WHERE game_id=? ORDER BY source_event_id, rowid",
            (game_id,),
        ).fetchall()]
        history = [
            {**dict(row), "structured": json.loads(row["structured_json"])}
            for row in conn.execute(
                "SELECT * FROM character_history WHERE game_id=? "
                "ORDER BY source_event_id, id", (game_id,)
            ).fetchall()
        ]
        events = [
            {"kind": row["kind"], "payload": json.loads(row["payload_json"])}
            for row in conn.execute(
                "SELECT kind, payload_json FROM events "
                "WHERE game_id=? AND kind='scene_activated' ORDER BY id", (game_id,)
            ).fetchall()
        ]
        context = make_decision_context(
            case, social, plans, knowledge, history, events, game["roll_count"]
        )
        context["game_id"] = game_id
        return context

    def invalidate_fact(self, game_id: str, fact_id: str, reason: str) -> None:
        """追加失效事件并同步投影；事实和来源历史不会被删除。"""
        with self.transaction() as conn:
            fact = conn.execute(
                "SELECT * FROM case_facts WHERE game_id=? AND fact_id=? AND status='active'",
                (game_id, fact_id),
            ).fetchone()
            case = conn.execute(
                "SELECT * FROM case_states WHERE game_id=?", (game_id,)
            ).fetchone()
            if fact is None or case is None:
                raise KeyError("有效事实或案件不存在")
            cursor = conn.execute(
                "INSERT INTO events(game_id, action_id, kind, payload_json) VALUES (?, NULL, ?, ?)",
                (
                    game_id,
                    "fact_invalidated",
                    json.dumps({"fact_id": fact_id, "reason": reason}, ensure_ascii=False),
                ),
            )
            event_id = cursor.lastrowid
            conn.execute(
                """
                UPDATE case_facts SET status='invalidated', invalidated_event_id=?
                WHERE game_id=? AND fact_id=?
                """,
                (event_id, game_id, fact_id),
            )
            clues = [clue for clue in json.loads(case["clues_json"]) if clue != fact_id]
            revision = case["revision"] + 1
            conn.execute(
                """
                UPDATE case_states SET clues_json=?, revision=?, updated_at=CURRENT_TIMESTAMP
                WHERE game_id=?
                """,
                (json.dumps(clues, ensure_ascii=False), revision, game_id),
            )
            conn.execute(
                "INSERT INTO events(game_id, action_id, kind, payload_json) VALUES (?, NULL, ?, ?)",
                (
                    game_id,
                    "case_changed",
                    json.dumps(
                        {
                            "phase": case["phase"], "location": case["location"],
                            "clock": case["clock"], "clues": clues,
                            "ending": case["ending"], "revision": revision,
                        },
                        ensure_ascii=False,
                    ),
                ),
            )

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
        structured_changes: dict | None = None,
        expected_decision_context_hash: str | None = None,
        director: dict | None = None,
    ) -> dict:
        """事务内复核版本、随机序号和决策上下文，再提交全部领域状态。"""
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
            # 事务内按存档案件解析固定内容，隔离两案行动与场景。
            from app.case_registry import get_case

            bundle = get_case(game["case_id"] if game["case_id"] else "C01")
            current_case = conn.execute(
                "SELECT * FROM case_states WHERE game_id=?", (game_id,)
            ).fetchone()
            current_revision = current_case["revision"] if current_case else 0
            if expected_revision is not None and current_revision != expected_revision:
                raise StateConflict("案件状态已变化，请重新预览")
            if expected_roll_count is not None and game["roll_count"] != expected_roll_count:
                raise StateConflict("随机序号已变化，请重新预览")
            if expected_decision_context_hash is not None:
                from app.npc_decision import decision_context_hash

                current_context = self._decision_context_from_conn(conn, game_id)
                if decision_context_hash(current_context) != expected_decision_context_hash:
                    raise StateConflict("决策上下文已变化，请重新预览")

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
            cursor = conn.execute(
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
            # 只有已接受提案才写事件；与行动共用同一事务，拒绝时不产生部分写入。
            if director is not None and director.get("accepted"):
                from app.director import director_event_payload

                conn.execute(
                    "INSERT INTO events(game_id, action_id, kind, payload_json) VALUES (?, ?, ?, ?)",
                    (
                        game_id,
                        action_id,
                        "director_beat",
                        json.dumps(director_event_payload(director), ensure_ascii=False),
                    ),
                )
            if structured_changes is not None:
                self._apply_structured_changes(
                    conn,
                    game_id,
                    cursor.lastrowid,
                    current_case,
                    case_state,
                    structured_changes,
                )
            if case_state:
                next_revision = current_revision + 1
                next_world_time = case_state.get(
                    "world_time", current_case["world_time"] if current_case else 0
                )
                conn.execute(
                    "UPDATE games SET location=? WHERE id=?",
                    (case_state["location"], game_id),
                )
                conn.execute(
                    """
                    INSERT INTO case_states(
                        game_id, phase, location, clock, world_time,
                        clues_json, ending, revision
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(game_id) DO UPDATE SET
                        phase=excluded.phase,
                        location=excluded.location,
                        clock=excluded.clock,
                        world_time=excluded.world_time,
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
                        next_world_time,
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
                                "world_time": next_world_time,
                                "clues": list(case_state["clues"]),
                                "ending": case_state["ending"],
                                "revision": next_revision,
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )
            # 城市时段按行动条数推进：每次提交都记录一条有界公开日程摘要。
            schedule_index = conn.execute(
                "SELECT COUNT(*) FROM actions WHERE game_id=?", (game_id,)
            ).fetchone()[0]
            offscreen = build_offscreen_payload(schedule_index)
            if offscreen is not None:
                conn.execute(
                    "INSERT INTO events(game_id, action_id, kind, payload_json) "
                    "VALUES (?, ?, 'offscreen_activity', ?)",
                    (game_id, action_id, json.dumps(offscreen, ensure_ascii=False)),
                )
            if structured_changes is not None:
                self._apply_social_changes(
                    conn, game_id, action_id, structured_changes.get("social", {})
                )
                self._apply_simulation_changes(
                    conn,
                    game_id,
                    action_id,
                    structured_changes.get("simulation", {}),
                    structured_changes.get("world_time", {}).get("after", 0),
                )
                self._apply_scene_changes(
                    conn, game_id, action_id, structured_changes.get("scenes", []), bundle
                )
        return self.get_action(game_id, action_id)

    @staticmethod
    def _apply_structured_changes(
        conn: sqlite3.Connection,
        game_id: str,
        source_event_id: int,
        current_case: sqlite3.Row | None,
        case_state: dict | None,
        changes: dict,
    ) -> None:
        """校验行动声明与实际投影一致，再写入可追溯结构化记录。"""
        facts = changes.get("facts_add", [])
        clock = changes.get("clock")
        knowledge = changes.get("knowledge", [])
        if (facts or clock) and case_state is None:
            raise ValueError("事实或 Clock 变化缺少案件投影")

        old_clues = set(json.loads(current_case["clues_json"])) if current_case else set()
        old_clock = current_case["clock"] if current_case else 0
        world_time = changes.get("world_time")
        if world_time is not None:
            old_world_time = current_case["world_time"] if current_case else 0
            actual_world_time = (
                case_state.get("world_time", old_world_time)
                if case_state is not None else old_world_time
            )
            if (
                world_time["before"] != old_world_time
                or world_time["after"] != actual_world_time
                or world_time["before"] + world_time["time_cost"] != world_time["after"]
            ):
                raise ValueError("游戏时间前后值、耗时与案件投影不一致")
        if case_state is not None:
            new_clues = set(case_state["clues"])
            if set(fact["fact_id"] for fact in facts) != new_clues - old_clues:
                raise ValueError("新增事实超出本次行动声明")
            if old_clues - new_clues:
                raise ValueError("事实失效必须使用独立失效事件")
            actual_delta = case_state["clock"] - old_clock
            if clock is None and actual_delta:
                raise ValueError("Clock 变化缺少结构化声明")
            if clock is not None and (
                clock["before_value"] != old_clock
                or clock["after_value"] != case_state["clock"]
                or clock["delta"] != actual_delta
            ):
                raise ValueError("Clock 前后值、增量与案件投影不一致")

        for fact in facts:
            conn.execute(
                """
                INSERT INTO case_facts(
                    game_id, fact_id, subject_id, fact_kind, source_event_id,
                    visibility, status, mechanical_json
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
                """,
                (
                    game_id,
                    fact["fact_id"],
                    fact.get("subject_id", "C01"),
                    fact.get("fact_kind", "clue"),
                    source_event_id,
                    fact.get("visibility", "player"),
                    json.dumps(fact.get("mechanical", {}), ensure_ascii=False),
                ),
            )

        if clock is not None:
            if (
                "source_event_id" in clock
                and clock["source_event_id"] != source_event_id
            ):
                raise ValueError("Clock 必须关联本次来源事件")
            if clock["before_value"] + clock["delta"] != clock["after_value"]:
                raise ValueError("Clock 前后值与增量不一致")
            conn.execute(
                """
                INSERT INTO clock_changes(
                    game_id, clock_id, source_event_id, reason,
                    delta, before_value, after_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_id,
                    clock["clock_id"],
                    source_event_id,
                    clock["reason"],
                    clock["delta"],
                    clock["before_value"],
                    clock["after_value"],
                ),
            )

        for record in knowledge:
            Database._insert_knowledge_record(
                conn, game_id, source_event_id, record
            )

    @staticmethod
    def _insert_knowledge_record(conn, game_id, source_event_id, record):
        """校验同档同持有者来源与纠正顺序，再写入不可变认知记录。"""
        kind = record.get("kind")
        precision = record.get("precision", "unknown")
        holder_id = record.get("holder_id")
        if kind not in {"observation", "memory", "testimony"}:
            raise ValueError("认知记录类型非法")
        if precision not in {"exact", "vague", "fragmentary", "unknown"}:
            raise ValueError("认知精度枚举非法")
        if record.get("visibility") not in {"public", "player", "private"}:
            raise ValueError("认知可见性非法")
        observed_at = record.get("observed_at")
        if (
            kind in {"observation", "memory"} and precision != "unknown"
            and (type(observed_at) is not int or observed_at < 0)
        ):
            raise ValueError("新观察或记忆必须有合法观察时间")
        source_id = record.get("source_record_id")
        if kind in {"memory", "testimony"} and precision != "unknown" and not source_id:
            raise ValueError("新记忆或证词必须有明确认知来源")
        if source_id is not None:
            source = conn.execute(
                "SELECT holder_id, source_event_id FROM knowledge_records "
                "WHERE id=? AND game_id=?",
                (source_id, game_id),
            ).fetchone()
            if source is None or source["holder_id"] != holder_id:
                raise ValueError("认知来源必须存在且属于同一持有者")
            if source["source_event_id"] > source_event_id:
                raise ValueError("认知来源事件不能晚于当前记录")
        target_id = record.get("corrects_record_id")
        if target_id is not None:
            target = conn.execute(
                "SELECT holder_id, source_event_id FROM knowledge_records "
                "WHERE id=? AND game_id=?",
                (target_id, game_id),
            ).fetchone()
            if target is None or target["holder_id"] != holder_id:
                raise ValueError("纠正目标必须存在且属于同一持有者")
            if target_id == record.get("id") or target["source_event_id"] >= source_event_id:
                raise ValueError("纠正目标必须早于当前记录且不能自指")
            if record.get("fact_id") is not None:
                raise ValueError("追加纠正不能授予新的事实")
        conn.execute(
            """
            INSERT INTO knowledge_records(
                id, game_id, holder_id, kind, source_event_id,
                fact_id, content, accuracy, visibility,
                source_record_id, observed_at, precision, corrects_record_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.get("id") or uuid.uuid4().hex,
                game_id,
                holder_id,
                kind,
                source_event_id,
                record.get("fact_id"),
                record["content"],
                record["accuracy"],
                record["visibility"],
                source_id,
                observed_at,
                precision,
                target_id,
            ),
        )

    @staticmethod
    def _insert_history(
        conn: sqlite3.Connection,
        game_id: str,
        source_event_id: int,
        record: dict,
    ) -> None:
        """写入同源履历，并在数据库约束前给出可读的领域异常。"""
        allowed_kinds = {"relationship", "trust", "condition", "social_memory", "plan"}
        if record.get("kind") not in allowed_kinds:
            raise ValueError("履历类型非法")
        if record.get("visibility") not in {"public", "player", "private"}:
            raise ValueError("履历可见性非法")
        conn.execute(
            """
            INSERT INTO character_history(
                game_id, holder_id, kind, content, structured_json,
                visibility, source_event_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                game_id,
                record["holder_id"],
                record["kind"],
                record["content"],
                json.dumps(record.get("structured", {}), ensure_ascii=False),
                record["visibility"],
                source_event_id,
            ),
        )

    @staticmethod
    def _apply_social_changes(
        conn: sqlite3.Connection,
        game_id: str,
        action_id: str,
        social: dict,
    ) -> None:
        """社会状态、履历和计划共享一个非私密摘要事件来源。"""
        states = social.get("states", [])
        history = social.get("history", [])
        plans = social.get("plans", [])
        if not (states or history or plans):
            return
        cursor = conn.execute(
            "INSERT INTO events(game_id, action_id, kind, payload_json) VALUES (?, ?, ?, ?)",
            (
                game_id,
                action_id,
                "social_changed",
                json.dumps({"changes": social.get("public", [])}, ensure_ascii=False),
            ),
        )
        event_id = cursor.lastrowid
        for state in states:
            kind = state.get("kind")
            if kind not in {"relationship", "trust", "condition"}:
                raise ValueError("社会状态类型非法")
            if kind == "trust" and (
                not isinstance(state.get("value_int"), int)
                or not -2 <= state["value_int"] <= 2
            ):
                raise ValueError("信任值必须位于 -2 至 +2")
            if kind == "condition" and state.get("expires_at") is None:
                raise ValueError("短期社会状态必须有到期时间")
            if state.get("visibility") not in {"public", "player", "private"}:
                raise ValueError("社会状态可见性非法")
            conn.execute(
                """
                INSERT INTO social_states(
                    game_id, state_id, holder_id, target_id, kind,
                    value_int, value_text, visibility, starts_at, expires_at,
                    status, source_event_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_id,
                    state["state_id"],
                    state["holder_id"],
                    state.get("target_id"),
                    kind,
                    state.get("value_int"),
                    state.get("value_text"),
                    state["visibility"],
                    state["starts_at"],
                    state.get("expires_at"),
                    state.get("status", "active"),
                    event_id,
                ),
            )
        for record in history:
            Database._insert_history(conn, game_id, event_id, record)
        for plan in plans:
            if plan.get("status") != "pending" or not isinstance(plan.get("due_time"), int):
                raise ValueError("固定计划状态或到期时间非法")
            conn.execute(
                """
                INSERT INTO local_plans(
                    game_id, plan_id, holder_id, scope, due_time,
                    status, source_event_id
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    game_id,
                    plan["plan_id"],
                    plan["holder_id"],
                    plan["scope"],
                    plan["due_time"],
                    event_id,
                ),
            )

    @staticmethod
    def _apply_simulation_changes(
        conn: sqlite3.Connection,
        game_id: str,
        action_id: str,
        simulation: dict,
        after_time: int,
    ) -> None:
        """只有真实到期事项才生成局部模拟事件及其同源产物。"""
        plans = simulation.get("plans", [])
        states = simulation.get("states", [])
        knowledge = simulation.get("knowledge", [])
        history = simulation.get("history", [])
        if not (plans or states or knowledge or history):
            return
        cursor = conn.execute(
            "INSERT INTO events(game_id, action_id, kind, payload_json) VALUES (?, ?, ?, ?)",
            (
                game_id,
                action_id,
                "local_simulation_advanced",
                json.dumps(
                    {
                        "world_time": after_time,
                        "completed_plans": [item["plan_id"] for item in plans],
                        "ended_states": [item["state_id"] for item in states],
                        "changes": simulation.get("public", []),
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        event_id = cursor.lastrowid
        for plan in plans:
            current = conn.execute(
                "SELECT * FROM local_plans WHERE game_id=? AND plan_id=?",
                (game_id, plan["plan_id"]),
            ).fetchone()
            if (
                current is None or current["status"] != "pending"
                or current["due_time"] > after_time or plan.get("status") != "completed"
            ):
                raise ValueError("计划到期时间与当前投影不一致")
            conn.execute(
                """
                UPDATE local_plans SET status='completed', completed_event_id=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE game_id=? AND plan_id=?
                """,
                (event_id, game_id, plan["plan_id"]),
            )
        for state in states:
            current = conn.execute(
                "SELECT * FROM social_states WHERE game_id=? AND state_id=?",
                (game_id, state["state_id"]),
            ).fetchone()
            if (
                current is None or current["status"] != "active"
                or current["expires_at"] is None or current["expires_at"] > after_time
                or state.get("status") != "ended"
            ):
                raise ValueError("短期状态到期时间与当前投影不一致")
            conn.execute(
                """
                UPDATE social_states SET status='ended', ended_event_id=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE game_id=? AND state_id=?
                """,
                (event_id, game_id, state["state_id"]),
            )
        for record in knowledge:
            Database._insert_knowledge_record(conn, game_id, event_id, record)
        for record in history:
            Database._insert_history(conn, game_id, event_id, record)

    @staticmethod
    def _apply_scene_changes(
        conn: sqlite3.Connection,
        game_id: str,
        action_id: str,
        scenes: list[dict],
        case,
    ) -> None:
        """只持久化固定场景的公开选择事实，不保存评分或私密知识。"""
        from app.action_protocol import RULES_VERSION

        expected_keys = {
            "scene_id", "plan_id", "holder_id", "candidate_id", "channel",
            "presentation_key", "rules_version", "content_version",
        }
        for scene in scenes:
            if set(scene) != expected_keys:
                raise ValueError("场景事件字段不完整或包含未声明字段")
            definition = next(
                (item for item in case.scene_definitions if item["scene_id"] == scene["scene_id"]),
                None,
            )
            if definition is None or any(
                scene[key] != definition[key]
                for key in ("plan_id", "candidate_id", "channel", "presentation_key")
            ):
                raise ValueError("场景事件与固定内容定义不一致")
            if (
                scene["rules_version"] != RULES_VERSION
                or scene["content_version"] != case.content_version
            ):
                raise ValueError("场景事件版本与当前规则不一致")
            conn.execute(
                "INSERT INTO events(game_id, action_id, kind, payload_json) "
                "VALUES (?, ?, 'scene_activated', ?)",
                (game_id, action_id, json.dumps(scene, ensure_ascii=False)),
            )

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

    def get_hypotheses(self, game_id: str) -> list[dict]:
        """按创建顺序读取玩家私人假设。"""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM player_hypotheses WHERE game_id=? ORDER BY created_at, rowid",
                (game_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_hypothesis(self, game_id: str, hypothesis_id: str) -> dict:
        """读取限定于当前存档的假设，防止跨存档修改。"""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM player_hypotheses WHERE game_id=? AND id=?",
                (game_id, hypothesis_id),
            ).fetchone()
        if row is None:
            raise KeyError("假设不存在")
        return dict(row)

    def create_hypothesis(self, game_id: str, text: str) -> dict:
        """在独立事务中新增文本假设，不触碰案件状态。"""
        self.get_game(game_id)
        hypothesis_id = uuid.uuid4().hex
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO player_hypotheses(id, game_id, text) VALUES (?, ?, ?)",
                (hypothesis_id, game_id, text),
            )
        return self.get_hypothesis(game_id, hypothesis_id)

    def update_hypothesis(self, game_id: str, hypothesis_id: str, text: str) -> dict:
        """在独立事务中修改当前存档拥有的假设。"""
        self.get_game(game_id)
        with self.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE player_hypotheses SET text=?, updated_at=CURRENT_TIMESTAMP
                WHERE game_id=? AND id=?
                """,
                (text, game_id, hypothesis_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("假设不存在")
        return self.get_hypothesis(game_id, hypothesis_id)

    def delete_hypothesis(self, game_id: str, hypothesis_id: str) -> None:
        """在独立事务中删除玩家假设，不产生世界事件。"""
        self.get_game(game_id)
        with self.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM player_hypotheses WHERE game_id=? AND id=?",
                (game_id, hypothesis_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("假设不存在")

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
            visible_knowledge_ids = {
                row[0] for row in conn.execute(
                    "SELECT id FROM knowledge_records WHERE game_id=? AND visibility='player'",
                    (game_id,),
                ).fetchall()
            }

        def public_record(item):
            source_id = item.get("source_record_id")
            target_id = item.get("corrects_record_id")
            return {
                "knowledge_id": item.get("knowledge_id") or item.get("id"),
                "holder_id": item.get("holder_id"),
                "kind": item.get("kind"),
                "content": item.get("content"),
                "accuracy": item.get("accuracy"),
                "visibility": item.get("visibility"),
                "precision": item.get("precision", "unknown"),
                "source_record_id": source_id if source_id in visible_knowledge_ids else None,
                "corrects_record_id": target_id if target_id in visible_knowledge_ids else None,
            }

        events_by_action = {}
        for event in event_rows:
            events_by_action.setdefault(event["action_id"], []).append(dict(event))
        result = []
        for row in rows:
            action = self._decode_action(row)
            audit = action["audit"]
            structured = audit.get("structured_changes") or {}
            social = structured.get("social")
            if social:
                # 审计接口同样是玩家视图，私密信任与记忆只保存在内部记录中。
                social["states"] = [
                    item for item in social.get("states", [])
                    if item.get("visibility") in {"public", "player"}
                ]
                social["history"] = [
                    item for item in social.get("history", [])
                    if item.get("visibility") in {"public", "player"}
                ]
            structured["knowledge"] = [
                public_record(item) for item in structured.get("knowledge", [])
                if item.get("visibility") == "player"
            ]
            simulation = structured.get("simulation")
            if simulation:
                simulation["knowledge"] = [
                    public_record(item) for item in simulation.get("knowledge", [])
                    if item.get("visibility") == "player"
                ]
            cognition = audit.get("cognition")
            if cognition:
                audit["cognition"] = {
                    "world_time": cognition.get("world_time"),
                    "records": [
                        public_record(item) for item in cognition.get("records", [])
                        if item.get("visibility") == "player"
                    ],
                    "decay": [],
                }
            autonomy = audit.get("autonomy")
            if autonomy:
                # 玩家只看公开回应和最终选择，内部知识、评分及排除理由不下发。
                audit["autonomy"] = {
                    "responses": [
                        {
                            key: item.get(key) for key in (
                                "response_id", "response_kind", "reason_codes",
                                "public_text_key",
                            )
                        }
                        for item in autonomy.get("responses", [])
                    ],
                    "decisions": [
                        {
                            key: item.get(key) for key in (
                                "plan_id", "holder_id", "selected_candidate_id",
                                "selection_reason_codes",
                            )
                        }
                        for item in autonomy.get("decisions", [])
                    ],
                    "scenes": [
                        {
                            key: item.get(key)
                            for key in ("scene_id", "candidate_id", "selected")
                        }
                        for item in autonomy.get("scenes", []) if item.get("selected")
                    ],
                }
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
        if audit.get("audit_version") in {1, 2, 3, 4}:
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
