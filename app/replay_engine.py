"""程序说明：只读提取历史，在命名内存 SQLite 中按保存命令、意图和骰点校验机械回放。"""

import hashlib
import json
import sqlite3
import time
import uuid

from app.action_pipeline import (
    apply_plan,
    build_structured_changes,
    make_audit,
    prepare_recorded_action,
)
from app.action_protocol import (
    PermissionDenied,
    RULES_VERSION,
    StateConflict,
    make_request_hash,
)
from app.case_content import CONTENT_VERSION, initial_cognition
from app.case_engine import action_by_id, initial_state
from app.npc_decision import decision_context_hash
from app.rules import classify_roll
from app.store import Database


class ReplayUnavailable(RuntimeError):
    """表示缺少可校验输入，不能与真实机械不一致混为一谈。"""

    def __init__(self, code: str, message: str, action: dict | None = None, index: int = 0):
        super().__init__(message)
        self.code = code
        self.message = message
        self.action = action
        self.index = index


def canonical_json(value) -> str:
    """生成跨物理主键和时间戳稳定的规范化 JSON。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def snapshot_hash(snapshot_json: str) -> str:
    """对规范化快照文本计算 SHA-256。"""
    return hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()


def make_initial_snapshot(protagonist: str) -> dict:
    """构造 v5 新档的空历史机械基线。"""
    return {
        "game": {
            "protagonist": protagonist,
            "location": "OC-01",
            "seed": 20261103,
            "roll_count": 0,
        },
        "case": initial_state(),
        "facts": [],
        "clock_changes": [],
        "knowledge": [],
        "social_states": [],
        "character_history": [],
        "local_plans": [],
    }


def compare_snapshots(expected, actual, path: str = "") -> list[dict]:
    """递归比较规范化投影，并按字段路径返回稳定差异顺序。"""
    if type(expected) is not type(actual):
        return [{"path": path, "expected": expected, "actual": actual}]
    if isinstance(expected, dict):
        differences = []
        for key in sorted(set(expected) | set(actual)):
            child_path = f"{path}.{key}" if path else key
            if key not in expected:
                differences.append({"path": child_path, "expected": None, "actual": actual[key]})
            elif key not in actual:
                differences.append({"path": child_path, "expected": expected[key], "actual": None})
            else:
                differences.extend(compare_snapshots(expected[key], actual[key], child_path))
        return differences
    if isinstance(expected, list):
        differences = []
        for index in range(max(len(expected), len(actual))):
            child_path = f"{path}[{index}]"
            if index >= len(expected):
                differences.append({"path": child_path, "expected": None, "actual": actual[index]})
            elif index >= len(actual):
                differences.append({"path": child_path, "expected": expected[index], "actual": None})
            else:
                differences.extend(
                    compare_snapshots(expected[index], actual[index], child_path)
                )
        return differences
    if expected != actual:
        return [{"path": path, "expected": expected, "actual": actual}]
    return []


class ReplayEngine:
    """执行一次性只读提取和隔离重算；不持有回放后的数据库连接。"""

    def __init__(
        self,
        database: Database,
        max_actions: int = 500,
        timeout_seconds: float = 10.0,
        clock=time.monotonic,
    ):
        self.db = database
        self.max_actions = max_actions
        self.timeout_seconds = timeout_seconds
        self.clock = clock

    def timeline(self, game_id: str) -> dict:
        """返回玩家可见历史，不透传完整快照、内部审计或私密社会记录。"""
        records = self._extract(game_id)
        items = []
        opening = next(
            (event for event in records["events"] if event["kind"] == "game_started"),
            None,
        )
        if opening:
            items.append({
                "kind": "game_started",
                "text": opening["payload"].get("text", "开场已记录"),
            })

        events_by_action = {}
        for event in records["events"]:
            if event["action_id"]:
                events_by_action.setdefault(event["action_id"], []).append(event)
        world_time = 0
        for index, action in enumerate(records["actions"], 1):
            events = events_by_action.get(action["id"], [])
            for event in events:
                if event["kind"] == "case_changed":
                    world_time = event["payload"].get("world_time", world_time)
            audit = action.get("audit") or {}
            revision = audit.get("state_revision") or {}
            response = action.get("response") or {}
            intent = action.get("intent") or {}
            items.append({
                "kind": "action",
                "action_index": index,
                "action_id": action["id"],
                "input": (action.get("command") or {}).get("text", action["input_text"]),
                "selected_action": {
                    key: intent.get(key)
                    for key in ("kind", "action_id", "label", "tendency", "requires_roll", "modifier")
                },
                "status": action["status"],
                "roll": action.get("roll"),
                "narrative": response.get("narrative"),
                "revision_before": revision.get("before"),
                "revision_after": revision.get("after"),
                "world_time": world_time,
                "rules_version": action.get("rules_version") or "legacy",
                "content_version": action.get("content_version") or "legacy",
                "events": [self._public_event(event) for event in events],
            })

        for event in records["events"]:
            if event["action_id"] is None and event["kind"].startswith("legacy_"):
                items.append({
                    "kind": event["kind"],
                    "event": self._public_event(event),
                })
        return {"baseline": self._public_baseline(records["baseline"]), "items": items}

    def verify(self, game_id: str, through_action_id: str | None = None) -> dict:
        """校验到指定行动；可预期失败统一转为三类公开结果。"""
        try:
            records = self._extract(game_id)
        except ReplayUnavailable as exc:
            return self._unavailable(self._public_baseline(None), through_action_id, exc)

        baseline = self._public_baseline(records["baseline"])
        actions = records["actions"]
        if through_action_id is None:
            target_count = len(actions)
            through_action_id = actions[-1]["id"] if actions else None
        else:
            target_count = next(
                (index for index, action in enumerate(actions, 1)
                 if action["id"] == through_action_id),
                None,
            )
            if target_count is None:
                raise KeyError("目标行动不存在")
        prefix = actions[:target_count]

        try:
            snapshot = self._validate_baseline(records["baseline"])
            self._validate_events(records, target_count)
            if len(prefix) > self.max_actions:
                raise ReplayUnavailable(
                    "replay_budget_exceeded", "目标前缀超过单次回放行动上限"
                )
            rolls = self._validate_actions(prefix)
        except ReplayUnavailable as exc:
            return self._unavailable(baseline, through_action_id, exc)

        deadline = self.clock() + self.timeout_seconds
        uri = f"file:replay-{uuid.uuid4().hex}?mode=memory&cache=shared"
        keeper = None
        checked = 0
        try:
            # keeper 保证所有 Database 短连接关闭后，命名内存库仍然存活。
            keeper = sqlite3.connect(uri, uri=True)
            memory = Database(uri).initialize()
            self._restore_baseline(memory, game_id, snapshot)

            for index, action in enumerate(prefix, 1):
                if self.clock() > deadline:
                    raise ReplayUnavailable(
                        "replay_budget_exceeded", "回放单调时钟期限已耗尽", action, index
                    )
                game = memory.get_game(game_id)
                case = memory.get_case_state(game_id)
                social = memory.get_social_states(game_id)
                plans = memory.get_local_plans(game_id)
                decision_context = memory.get_decision_context(game_id)
                command = action["command"]
                roll = rolls[index - 1]
                try:
                    plan = prepare_recorded_action(
                        command, action["intent"], case, social, plans, decision_context
                    )
                    if not plan["can_submit"]:
                        return self._mismatch(
                            baseline, through_action_id, checked, action, index,
                            [{"path": "permission.can_submit", "expected": True, "actual": False}],
                        )
                    next_case = apply_plan(plan, case, roll)
                    structured = None
                    if plan["case_action"]:
                        content = action_by_id(plan["intent"]["action_id"])
                        structured = build_structured_changes(
                            content, case, roll["outcome"] if roll else "no_roll", social, plans,
                            decision_context,
                        )
                    context_hash = decision_context_hash(decision_context)
                    audit = make_audit(
                        plan, game, case, roll, next_case, structured, context_hash
                    )
                    memory.commit_action(
                        game_id,
                        f"replay:{index}",
                        command["text"],
                        action["intent"],
                        roll,
                        next_case,
                        request_hash=make_request_hash(game_id, command),
                        expected_revision=(
                            case["revision"]
                            if command.get("expected_revision") is None
                            else command["expected_revision"]
                        ),
                        expected_roll_count=game["roll_count"],
                        command=command,
                        declaration=plan["declaration"],
                        audit=audit,
                        structured_changes=structured,
                        expected_decision_context_hash=context_hash,
                    )
                except (PermissionDenied, StateConflict, ValueError):
                    return self._mismatch(
                        baseline, through_action_id, checked, action, index,
                        [{"path": "permission.can_submit", "expected": True, "actual": False}],
                    )

                actual_records = self._read_current(memory, game_id)
                actual = self._canonical_snapshot(actual_records, index, snapshot, False)
                expected = self._canonical_snapshot(records, index, snapshot, False)
                differences = compare_snapshots(expected, actual)
                # 最新边界还要核对当前 games/case_states 和各领域当前状态。
                if not differences and index == len(actions):
                    current = self._canonical_snapshot(records, index, snapshot, True)
                    differences = compare_snapshots(expected, current)
                if differences:
                    return self._mismatch(
                        baseline, through_action_id, checked, action, index, differences,
                        expected, actual,
                    )
                checked = index
                if self.clock() > deadline:
                    raise ReplayUnavailable(
                        "replay_budget_exceeded", "回放单调时钟期限已耗尽", action, index
                    )

            return {
                "status": "matched",
                "through_action_id": through_action_id,
                "checked_actions": checked,
                "baseline": baseline,
            }
        except ReplayUnavailable as exc:
            return self._unavailable(baseline, through_action_id, exc, checked)
        finally:
            if keeper is not None:
                keeper.close()

    def _extract(self, game_id: str) -> dict:
        """在强制只读连接的单一事务中取得一致性历史快照。"""
        uri = f"{self.db.path.resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            return self._read_records(conn, game_id)
        finally:
            conn.close()

    def _read_current(self, database: Database, game_id: str) -> dict:
        """读取无人并发写入的内存试算投影。"""
        with database.connect() as conn:
            conn.execute("BEGIN")
            return self._read_records(conn, game_id)

    @staticmethod
    def _read_records(conn: sqlite3.Connection, game_id: str) -> dict:
        """读取比较所需的全部表；玩家假设不属于世界机械状态。"""
        game = conn.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
        if game is None:
            raise KeyError("存档不存在")
        case = conn.execute("SELECT * FROM case_states WHERE game_id=?", (game_id,)).fetchone()
        baseline = conn.execute(
            "SELECT * FROM replay_baselines WHERE game_id=?", (game_id,)
        ).fetchone()
        records = {
            "game": dict(game),
            "case": ReplayEngine._decode_row(case) if case else None,
            "baseline": dict(baseline) if baseline else None,
        }
        tables = {
            "actions": "rowid",
            "events": "id",
            "case_facts": "rowid",
            "clock_changes": "id",
            "knowledge_records": "rowid",
            "social_states": "rowid",
            "character_history": "id",
            "local_plans": "rowid",
        }
        for table, order in tables.items():
            rows = conn.execute(
                f"SELECT rowid AS _rowid, * FROM {table} WHERE game_id=? ORDER BY {order}",
                (game_id,),
            ).fetchall()
            records[table] = [ReplayEngine._decode_row(row) for row in rows]
        return records

    @staticmethod
    def _decode_row(row: sqlite3.Row) -> dict:
        """反序列化记录；必要 JSON 损坏时明确降级为不可校验。"""
        result = dict(row)
        fields = {
            "payload_json": "payload",
            "command_json": "command",
            "intent_json": "intent",
            "declaration_json": "declaration",
            "audit_json": "audit",
            "roll_json": "roll",
            "response_json": "response",
            "mechanical_json": "mechanical",
            "structured_json": "structured",
            "clues_json": "clues",
        }
        for column, key in fields.items():
            if column not in result:
                continue
            raw = result[column]
            if raw is None:
                result[key] = None
                continue
            try:
                result[key] = json.loads(raw)
            except (TypeError, json.JSONDecodeError) as exc:
                raise ReplayUnavailable(
                    "invalid_action_record", f"记录字段 {column} 不是有效 JSON"
                ) from exc
        return result

    @staticmethod
    def _public_baseline(row: dict | None) -> dict:
        """只暴露基线元数据，不返回完整初始快照。"""
        return {
            "available": row is not None,
            "snapshot_format": row.get("snapshot_format") if row else None,
            "rules_version": row.get("rules_version") if row else None,
            "content_version": row.get("content_version") if row else None,
            "snapshot_hash": row.get("snapshot_hash") if row else None,
        }

    @staticmethod
    def _public_event(event: dict) -> dict:
        """按事件类型白名单生成公开摘要。"""
        kind = event["kind"]
        payload = event.get("payload") or {}
        allowed = {
            "action_committed": (),
            "case_changed": ("phase", "location", "clock", "world_time", "clues", "ending", "revision"),
            "social_changed": ("changes",),
            "local_simulation_advanced": ("world_time", "completed_plans", "changes"),
            "scene_activated": (
                "scene_id", "plan_id", "holder_id", "candidate_id",
                "channel", "presentation_key", "rules_version", "content_version",
            ),
            "narrative_completed": ("text",),
            "legacy_v3_backfill": ("phase", "location", "clock", "world_time", "clues", "ending", "revision"),
            "legacy_v4_backfill": ("world_time", "relationship"),
        }.get(kind, ())
        return {"kind": kind, **{key: payload.get(key) for key in allowed}}

    @staticmethod
    def _validate_baseline(row: dict | None) -> dict:
        """校验基线哈希、格式、版本和必要机械领域。"""
        if row is None:
            raise ReplayUnavailable("baseline_missing", "旧档缺少初始基线，仅可查看历史")
        if snapshot_hash(row["snapshot_json"]) != row["snapshot_hash"]:
            raise ReplayUnavailable("baseline_hash_mismatch", "初始快照哈希不一致")
        if row["snapshot_format"] != 1:
            raise ReplayUnavailable("unsupported_snapshot", "不支持的初始快照格式")
        if row["rules_version"] != RULES_VERSION or row["content_version"] != CONTENT_VERSION:
            raise ReplayUnavailable("unsupported_version", "当前程序不支持基线声明的版本")
        try:
            snapshot = json.loads(row["snapshot_json"])
        except json.JSONDecodeError as exc:
            raise ReplayUnavailable("unsupported_snapshot", "初始快照不是有效 JSON") from exc
        required_lists = (
            "facts", "clock_changes", "knowledge", "social_states",
            "character_history", "local_plans",
        )
        game = snapshot.get("game") if isinstance(snapshot, dict) else None
        case = snapshot.get("case") if isinstance(snapshot, dict) else None
        valid = (
            isinstance(game, dict)
            and all(key in game for key in ("protagonist", "location", "seed", "roll_count"))
            and isinstance(case, dict)
            and all(key in case for key in (
                "phase", "location", "clock", "world_time", "clues", "ending", "revision"
            ))
            and all(isinstance(snapshot.get(key), list) for key in required_lists)
            and all(snapshot[key] == [] for key in required_lists)
        )
        if not valid or canonical_json(snapshot) != row["snapshot_json"]:
            raise ReplayUnavailable("unsupported_snapshot", "初始快照缺少必要领域或不是 v1 空历史")
        return snapshot

    @staticmethod
    def _validate_actions(actions: list[dict]) -> list[dict | None]:
        """在试算前校验所有命令、意图、版本和保存骰点。"""
        rolls = []
        for index, action in enumerate(actions, 1):
            if action.get("rules_version") != RULES_VERSION or action.get("content_version") != CONTENT_VERSION:
                raise ReplayUnavailable(
                    "unsupported_version", "行动声明的版本不受支持", action, index
                )
            command = action.get("command")
            intent = action.get("intent")
            valid = (
                isinstance(command, dict)
                and command.get("kind") == "action.submit"
                and isinstance(command.get("text"), str)
                and command["text"] == action["input_text"]
                and isinstance(intent, dict)
                and isinstance(intent.get("kind"), str)
                and type(intent.get("requires_roll")) is bool
                and type(intent.get("modifier")) is int
            )
            if not valid:
                raise ReplayUnavailable(
                    "invalid_action_record", "行动缺少有效规范命令或意图", action, index
                )
            if intent["kind"] == "case_action":
                try:
                    content = action_by_id(intent.get("action_id"))
                except KeyError as exc:
                    raise ReplayUnavailable(
                        "invalid_action_record", "案件行动定义不存在", action, index
                    ) from exc
                if (
                    command.get("action_id") not in (None, content["id"])
                    or intent["requires_roll"] != content["requires_roll"]
                    or intent["modifier"] != content["modifier"]
                ):
                    raise ReplayUnavailable(
                        "invalid_action_record", "案件意图与固定内容不一致", action, index
                    )
            roll = action.get("roll")
            if intent["requires_roll"] != (roll is not None):
                raise ReplayUnavailable(
                    "invalid_action_record", "行动与骰点的存在性不一致", action, index
                )
            if roll is not None:
                dice = roll.get("dice") if isinstance(roll, dict) else None
                valid_roll = (
                    isinstance(dice, list)
                    and len(dice) == 2
                    and all(type(value) is int and 1 <= value <= 6 for value in dice)
                    and type(roll.get("modifier")) is int
                    and type(roll.get("total")) is int
                    and roll["modifier"] == intent["modifier"]
                    and roll["total"] == sum(dice) + roll["modifier"]
                    and roll.get("outcome") == classify_roll(roll["total"])
                )
                if not valid_roll:
                    raise ReplayUnavailable(
                        "invalid_action_record", "骰面、修正、总和或结果分档非法", action, index
                    )
            rolls.append(roll)
        return rolls

    @staticmethod
    def _validate_events(records: dict, target_count: int) -> None:
        """拒绝无法由行动命令重放的非行动机械变化。"""
        action_indexes = {
            action["id"]: index for index, action in enumerate(records["actions"], 1)
        }
        allowed = {
            "game_started", "action_committed", "case_changed", "social_changed",
            "local_simulation_advanced", "scene_activated", "narrative_completed",
        }
        current_boundary = 0
        for event in records["events"]:
            action_id = event["action_id"]
            if action_id is not None:
                if action_id not in action_indexes:
                    raise ReplayUnavailable(
                        "invalid_action_record", "事件关联了不存在的行动"
                    )
                current_boundary = action_indexes[action_id]
                if current_boundary <= target_count and event["kind"] not in allowed:
                    raise ReplayUnavailable(
                        "unsupported_external_mutation", "存在无法重放的行动机械事件"
                    )
            elif event["kind"] != "game_started" and current_boundary <= target_count:
                raise ReplayUnavailable(
                    "unsupported_external_mutation", "存在无法重放的非行动机械变化"
                )

    @staticmethod
    def _restore_baseline(memory: Database, game_id: str, snapshot: dict) -> None:
        """把已验证空历史基线恢复到内存库。"""
        game = snapshot["game"]
        case = snapshot["case"]
        with memory.transaction() as conn:
            conn.execute(
                "INSERT INTO games(id, protagonist, location, seed, roll_count) VALUES (?, ?, ?, ?, ?)",
                (
                    game_id, game["protagonist"], game["location"], game["seed"],
                    game["roll_count"],
                ),
            )
            cursor = conn.execute(
                "INSERT INTO events(game_id, action_id, kind, payload_json) VALUES (?, NULL, 'game_started', '{}')",
                (game_id,),
            )
            # 当前版本新档必须恢复与实时创建档完全相同的固定初始认知。
            for record in initial_cognition(game_id, cursor.lastrowid):
                Database._insert_knowledge_record(
                    conn, game_id, cursor.lastrowid, record
                )
            conn.execute(
                """
                INSERT INTO case_states(
                    game_id, phase, location, clock, world_time,
                    clues_json, ending, revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_id, case["phase"], case["location"], case["clock"],
                    case["world_time"], canonical_json(case["clues"]), case["ending"],
                    case["revision"],
                ),
            )

    @staticmethod
    def _canonical_snapshot(
        records: dict, boundary: int, baseline: dict, use_current: bool
    ) -> dict:
        """按行动边界重建语义投影，忽略物理 ID、时间戳和来源事件编号。"""
        action_indexes = {
            action["id"]: index for index, action in enumerate(records["actions"], 1)
        }
        event_sources = {}
        for event in records["events"]:
            if event["action_id"] in action_indexes:
                event_sources[event["id"]] = (
                    action_indexes[event["action_id"]], event["kind"]
                )

        def source(event_id):
            if event_id is None:
                return "baseline"
            index, kind = event_sources.get(event_id, (0, "unknown"))
            return f"{index}:{kind}"

        def included(event_id):
            return event_sources.get(event_id, (0, ""))[0] <= boundary

        case = dict(baseline["case"])
        for event in records["events"]:
            if (
                event["kind"] == "case_changed"
                and event["action_id"] in action_indexes
                and action_indexes[event["action_id"]] <= boundary
            ):
                payload = event["payload"]
                case = {
                    "phase": payload["phase"],
                    "location": payload["location"],
                    "clock": payload["clock"],
                    "world_time": payload.get("world_time", case.get("world_time", 0)),
                    "clues": list(payload["clues"]),
                    "ending": payload["ending"],
                    "revision": payload["revision"],
                }
        if use_current and records["case"] is not None:
            current = records["case"]
            case = {
                key: (list(current["clues"]) if key == "clues" else current[key])
                for key in ("phase", "location", "clock", "world_time", "clues", "ending", "revision")
            }
        case["clues"] = sorted(case["clues"])

        prefix = records["actions"][:boundary]
        game = {
            "location": case["location"],
            "seed": baseline["game"]["seed"],
            "roll_count": sum(action.get("roll") is not None for action in prefix),
        }
        if use_current:
            game = {
                "location": records["game"]["location"],
                "seed": records["game"]["seed"],
                "roll_count": records["game"]["roll_count"],
            }

        facts = {}
        for row in records["case_facts"]:
            if not included(row["source_event_id"]):
                continue
            invalidated = (
                row["invalidated_event_id"] is not None
                and included(row["invalidated_event_id"])
            )
            facts[row["fact_id"]] = {
                "subject_id": row["subject_id"],
                "fact_kind": row["fact_kind"],
                "source": source(row["source_event_id"]),
                "invalidated_source": source(row["invalidated_event_id"]) if invalidated else "baseline",
                "visibility": row["visibility"],
                "status": row["status"] if use_current else (
                    "invalidated" if invalidated else "active"
                ),
                "mechanical": row["mechanical"],
            }

        clock_changes = [
            {
                "clock_id": row["clock_id"],
                "source": source(row["source_event_id"]),
                "reason": row["reason"],
                "delta": row["delta"],
                "before_value": row["before_value"],
                "after_value": row["after_value"],
            }
            for row in records["clock_changes"] if included(row["source_event_id"])
        ]
        clock_changes.sort(key=canonical_json)

        knowledge = [
            {
                "knowledge_id": row.get("knowledge_id") or row["id"],
                "holder_id": row["holder_id"],
                "kind": row["kind"],
                "source": source(row["source_event_id"]),
                "source_record_id": row["source_record_id"],
                "observed_at": row["observed_at"],
                "precision": row["precision"],
                "corrects_record_id": row["corrects_record_id"],
                "fact_id": row["fact_id"],
                "content": row["content"],
                "accuracy": row["accuracy"],
                "visibility": row["visibility"],
            }
            for row in records["knowledge_records"] if included(row["source_event_id"])
        ]
        knowledge.sort(key=canonical_json)

        social_states = {}
        for row in records["social_states"]:
            if not included(row["source_event_id"]):
                continue
            ended = row["ended_event_id"] is not None and included(row["ended_event_id"])
            social_states[row["state_id"]] = {
                "holder_id": row["holder_id"],
                "target_id": row["target_id"],
                "kind": row["kind"],
                "value_int": row["value_int"],
                "value_text": row["value_text"],
                "visibility": row["visibility"],
                "starts_at": row["starts_at"],
                "expires_at": row["expires_at"],
                "status": row["status"] if use_current else ("ended" if ended else "active"),
                "source": source(row["source_event_id"]),
                "ended_source": source(row["ended_event_id"]) if ended else "baseline",
            }

        history = [
            {
                "holder_id": row["holder_id"],
                "kind": row["kind"],
                "content": row["content"],
                "structured": row["structured"],
                "visibility": row["visibility"],
                "source": source(row["source_event_id"]),
            }
            for row in records["character_history"] if included(row["source_event_id"])
        ]
        history.sort(key=canonical_json)

        local_plans = {}
        for row in records["local_plans"]:
            if not included(row["source_event_id"]):
                continue
            completed = (
                row["completed_event_id"] is not None
                and included(row["completed_event_id"])
            )
            local_plans[row["plan_id"]] = {
                "holder_id": row["holder_id"],
                "scope": row["scope"],
                "due_time": row["due_time"],
                "status": row["status"] if use_current else (
                    "completed" if completed else "pending"
                ),
                "source": source(row["source_event_id"]),
                "completed_source": source(row["completed_event_id"]) if completed else "baseline",
            }
        scenes = [
            {
                "source": source(event["id"]),
                **{
                    key: event["payload"].get(key) for key in (
                        "scene_id", "plan_id", "holder_id", "candidate_id", "channel",
                        "presentation_key", "rules_version", "content_version",
                    )
                },
            }
            for event in records["events"]
            if event["kind"] == "scene_activated"
            and event["action_id"] in action_indexes
            and action_indexes[event["action_id"]] <= boundary
        ]
        return {
            "game": game,
            "case": case,
            "facts": facts,
            "clock_changes": clock_changes,
            "knowledge": knowledge,
            "social_states": social_states,
            "character_history": history,
            "local_plans": local_plans,
            "scenes": scenes,
        }

    @staticmethod
    def _mismatch(
        baseline: dict,
        through_action_id: str | None,
        checked: int,
        action: dict,
        index: int,
        differences: list[dict],
        expected: dict | None = None,
        actual: dict | None = None,
    ) -> dict:
        """生成首个不一致的公开摘要，并裁剪所有私密字段差异。"""
        public = []
        private = False
        for difference in differences:
            if ReplayEngine._is_private_difference(difference, expected, actual):
                private = True
            else:
                public.append(difference)
        redacted = list(public)
        if private:
            redacted.append({"path": "private_state", "redacted": True})
        revision = (action.get("audit") or {}).get("state_revision") or {}
        return {
            "status": "mismatched",
            "through_action_id": through_action_id,
            "checked_actions": checked,
            "baseline": baseline,
            "first_mismatch": {
                "action_index": index,
                "action_id": action["id"],
                "input": action["input_text"],
                "revision_before": revision.get("before"),
                "revision_after": revision.get("after"),
                "differences": redacted,
            },
        }

    @staticmethod
    def _is_private_difference(
        difference: dict, expected: dict | None, actual: dict | None
    ) -> bool:
        """按对应记录的可见性判断差异，绝不返回私密前后值。"""
        path = difference["path"]
        if any(value in difference for value in ("expected", "actual")):
            for snapshot in (expected, actual):
                if not snapshot:
                    continue
                if path.startswith("social_states."):
                    state_id = path.split(".", 2)[1]
                    row = snapshot["social_states"].get(state_id)
                    if row and row.get("visibility") == "private":
                        return True
                for root in ("knowledge", "character_history"):
                    if path.startswith(f"{root}["):
                        try:
                            index = int(path.split("[", 1)[1].split("]", 1)[0])
                            row = snapshot[root][index]
                        except (ValueError, IndexError):
                            continue
                        if row.get("visibility") == "private":
                            return True
        return False

    @staticmethod
    def _unavailable(
        baseline: dict,
        through_action_id: str | None,
        error: ReplayUnavailable,
        checked: int = 0,
    ) -> dict:
        """返回稳定原因代码和首个受阻行动，不泄露内部快照。"""
        reason = {"code": error.code, "message": error.message}
        if error.action is not None:
            reason.update({
                "action_index": error.index,
                "action_id": error.action["id"],
            })
        return {
            "status": "unavailable",
            "through_action_id": through_action_id,
            "checked_actions": checked,
            "baseline": baseline,
            "reason": reason,
        }
