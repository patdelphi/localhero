"""程序说明：串行编排行动预览、程序判定、事务提交、审计和可重试叙事。"""

import json
import threading

from app.action_pipeline import (
    apply_plan,
    build_structured_changes,
    make_audit,
    prepare_action,
)
from app.action_protocol import (
    IdempotencyConflict,
    PermissionDenied,
    RULES_VERSION,
    StateConflict,
    make_command,
    make_request_hash,
    normalize_text,
)
from app.case_engine import action_by_id, public_state
from app.case_registry import case_for_game, get_case
from app.city_schedule import city_time, positions
from app.director import DEFAULT_INTERVAL, MAX_INTERVAL, MIN_INTERVAL, evaluate_director
from app.model import SimulationError
from app.narrative_context import (
    build_narrative_context,
    previous_narrative_texts,
    trim_context,
)
from app.replay_engine import ReplayEngine
from app.rules import roll_for_sequence
from app.store import Database


class GameService:
    """掌握行动顺序；模拟模型只提供意图和文字，不掌握游戏事实。"""

    def __init__(
        self,
        database: Database,
        model,
        director_enabled: bool = False,
        director_interval: int = DEFAULT_INTERVAL,
    ):
        self.db = database
        self.model = model
        self._lock = threading.RLock()
        # 界面开关只作用于当前进程，默认值来自 .env，不写入存档。
        self.director_default = bool(director_enabled)
        self.director_interval = max(MIN_INTERVAL, min(MAX_INTERVAL, int(director_interval)))
        self._director_overrides: dict[str, bool] = {}

    def create_game(self, protagonist: str, case_id: str | None = None) -> dict:
        """按指定案件创建新存档，未知案件编号由注册表拒绝。"""
        name = protagonist.strip()
        if not name:
            raise ValueError("主人公姓名不能为空")
        bundle = get_case(case_id)
        return self.db.create_game(name, bundle)

    def get_game(self, game_id: str) -> dict:
        """返回存档、案件公开状态及其完整事件历史。"""
        game = self.db.get_game(game_id)
        case = self.db.get_case_state(game_id)
        bundle = case_for_game(self.db, game_id)
        return {
            "game": game,
            "case": public_state(case, self.db.get_local_plans(game_id), bundle),
            "events": self.db.get_events(game_id),
        }

    def get_city(self, game_id: str) -> dict:
        """返回当前时段的玩家可见城市切片，不含私密行程或隐藏事实。"""
        self.db.get_game(game_id)  # 先校验存档是否存在
        revision = self.db.count_actions(game_id)
        # 只回传最近两条离屏摘要，避免面板随行动数无限增长。
        recent: list[dict] = []
        for event in reversed(self.db.get_events(game_id)):
            if event["kind"] != "offscreen_activity":
                continue
            recent.append(event.get("payload") or {})
            if len(recent) >= 2:
                break
        return {
            "city": city_time(revision),
            "positions": positions(revision),
            "offscreen": recent,
        }

    def create_branch(
        self, game_id: str, fork_action_id: str, label: str | None = None
    ) -> dict:
        """从指定行动分叉；串行锁避免与其他写操作争抢 SQLite。"""
        from app.branching import create_branch

        with self._lock:
            return create_branch(self.db, game_id, fork_action_id, label)

    def get_branches(self, game_id: str) -> dict:
        """返回分支树与各节点关键状态。"""
        from app.branching import branch_tree

        return branch_tree(self.db, game_id)

    def set_branch_status(
        self, game_id: str, status: str, confirm: bool = False
    ) -> dict:
        """归档或恢复分支；必须显式确认。"""
        from app.branching import set_branch_status

        with self._lock:
            return set_branch_status(self.db, game_id, status, confirm)

    def preview_action(
        self, game_id: str, text: str, action_id: str | None = None
    ) -> dict:
        """只读生成行动声明；不写库、不掷骰、不推进随机序号。"""
        action_text = normalize_text(text)
        if not action_text:
            raise ValueError("行动内容不能为空")
        with self._lock:
            self.db.get_game(game_id)
            bundle = case_for_game(self.db, game_id)
            case_state = self.db.get_case_state(game_id)
            social_states = self.db.get_social_states(game_id)
            local_plans = self.db.get_local_plans(game_id)
            decision_context = self.db.get_decision_context(game_id)
            plan = prepare_action(
                action_text, case_state, self.model, action_id, social_states, local_plans,
                decision_context, bundle,
            )
            return {
                "revision": case_state["revision"],
                "rules_version": RULES_VERSION,
                "content_version": bundle.content_version,
                "normalized_input": action_text,
                "selected_action": plan["selected_action"],
                "case_action": plan["case_action"],
                "candidates": plan["candidates"],
                "declaration": plan["declaration"],
                "mechanical_changes": plan["mechanical_changes"],
                "pipeline": plan["pipeline"],
                "permission": plan["permission"],
                "random": None,
                "can_submit": plan["can_submit"],
                "reason": plan["reason"],
            }

    def act(
        self,
        game_id: str,
        text: str,
        request_id: str,
        action_id: str | None = None,
        expected_revision: int | None = None,
    ) -> dict:
        """处理一次行动；同一请求哈希只提交一次事实。"""
        action_text = normalize_text(text)
        if not action_text:
            raise ValueError("行动内容不能为空")
        if not request_id.strip():
            raise ValueError("请求标识不能为空")
        command = make_command(action_text, action_id, expected_revision)
        request_hash = make_request_hash(game_id, command)

        with self._lock:
            existing = self.db.get_action_by_request(game_id, request_id)
            if existing:
                same_legacy_request = (
                    existing.get("request_hash") is None
                    and existing["input_text"] == action_text
                )
                if existing.get("request_hash") != request_hash and not same_legacy_request:
                    raise IdempotencyConflict("请求标识已用于不同命令")
                return self._response(existing)

            game = self.db.get_game(game_id)
            bundle = case_for_game(self.db, game_id)
            case_state = self.db.get_case_state(game_id)
            # 先识别过期预览，避免状态变化后的权限重验掩盖真正的并发冲突。
            if (
                expected_revision is not None
                and case_state["revision"] != expected_revision
            ):
                raise StateConflict("案件状态已变化，请重新预览")
            social_states = self.db.get_social_states(game_id)
            local_plans = self.db.get_local_plans(game_id)
            decision_context = self.db.get_decision_context(game_id)
            plan = prepare_action(
                action_text, case_state, self.model, action_id, social_states, local_plans,
                decision_context, bundle,
            )
            if not plan["can_submit"]:
                raise PermissionDenied(plan["reason"] or "行动未通过程序审核")

            roll = None
            if plan["intent"]["requires_roll"]:
                roll = roll_for_sequence(
                    game["seed"], game["roll_count"], plan["intent"]["modifier"]
                ).to_dict()
            next_case_state = apply_plan(plan, case_state, roll, bundle)
            structured_changes = None
            if plan["case_action"]:
                action_content = action_by_id(plan["intent"]["action_id"], bundle)
                outcome = roll["outcome"] if roll else "no_roll"
                structured_changes = build_structured_changes(
                    action_content, case_state, outcome, social_states, local_plans,
                    decision_context, bundle,
                )
            from app.npc_decision import decision_context_hash

            # 情节导演只提出有界节拍；关闭时不读取事件，保持第八阶段行为。
            director = None
            if self._director_enabled(game_id):
                director = evaluate_director(
                    self.db.get_events(game_id),
                    self.model,
                    plan["intent"],
                    case_state["location"],
                    self.director_interval,
                    True,
                    bundle,
                )

            context_hash = decision_context_hash(decision_context)
            audit = make_audit(
                plan, game, case_state, roll, next_case_state, structured_changes,
                context_hash, director, bundle,
            )
            submitted_revision = (
                case_state["revision"] if expected_revision is None else expected_revision
            )
            action = self.db.commit_action(
                game_id,
                request_id,
                action_text,
                plan["intent"],
                roll,
                next_case_state,
                request_hash=request_hash,
                expected_revision=submitted_revision,
                expected_roll_count=game["roll_count"],
                command=command,
                declaration=plan["declaration"],
                audit=audit,
                structured_changes=structured_changes,
                expected_decision_context_hash=context_hash,
                director=director,
            )
            return self._narrate_or_pending(action)

    def get_director_settings(self, game_id: str) -> dict:
        """返回当前存档可用的情节导演开关与触发参数。"""
        self.db.get_game(game_id)
        from app.director import BEAT_TYPES

        return {
            "enabled": self._director_enabled(game_id),
            "default_enabled": self.director_default,
            "interval": self.director_interval,
            "beat_types": list(BEAT_TYPES),
        }

    def set_director_enabled(self, game_id: str, enabled: bool) -> dict:
        """会话内切换开关；不写存档、不推进游戏或回放。"""
        self.db.get_game(game_id)
        if type(enabled) is not bool:
            raise ValueError("情节导演开关必须是布尔值")
        with self._lock:
            self._director_overrides[game_id] = enabled
        return self.get_director_settings(game_id)

    def _director_enabled(self, game_id: str) -> bool:
        """优先使用当前会话的界面开关，否则采用 .env 默认值。"""
        return self._director_overrides.get(game_id, self.director_default)

    def get_audit(self, game_id: str, limit: int = 50) -> dict:
        """读取有界审计列表，不暴露额外写入口。"""
        self.db.get_game(game_id)
        return {"items": self.db.get_audit(game_id, limit)}

    def get_timeline(self, game_id: str) -> dict:
        """读取玩家可见历史，不返回完整基线或私密机械记录。"""
        return ReplayEngine(self.db).timeline(game_id)

    def verify_replay(self, game_id: str, through_action_id: str | None = None) -> dict:
        """在独立内存库重算指定历史前缀，不调用模型或修改原档。"""
        return ReplayEngine(self.db).verify(game_id, through_action_id)

    def get_knowledge(self, game_id: str) -> dict:
        """返回玩家可见认知，不提供任意人物私密知识查询参数。"""
        self.db.get_game(game_id)
        return {"items": self.db.get_player_knowledge(game_id)}

    def get_character_history(self, game_id: str) -> dict:
        """只返回公开或明确授予玩家的人物履历。"""
        self.db.get_game(game_id)
        return {"items": self.db.get_character_history(game_id)}

    def get_hypotheses(self, game_id: str) -> dict:
        """读取当前存档的玩家假设。"""
        self.db.get_game(game_id)
        return {"items": self.db.get_hypotheses(game_id)}

    def create_hypothesis(self, game_id: str, text: str) -> dict:
        """保存非空文本假设，不调用模型或推进游戏。"""
        normalized = normalize_text(text)
        if not normalized:
            raise ValueError("假设内容不能为空")
        return self.db.create_hypothesis(game_id, normalized)

    def update_hypothesis(self, game_id: str, hypothesis_id: str, text: str) -> dict:
        """修改当前存档的非空文本假设。"""
        normalized = normalize_text(text)
        if not normalized:
            raise ValueError("假设内容不能为空")
        return self.db.update_hypothesis(game_id, hypothesis_id, normalized)

    def delete_hypothesis(self, game_id: str, hypothesis_id: str) -> None:
        """删除当前存档的玩家假设。"""
        self.db.delete_hypothesis(game_id, hypothesis_id)

    def retry_narrative(self, game_id: str, action_id: str) -> dict:
        """只重试叙事，不重新解析、掷骰或推进行动事实。"""
        with self._lock:
            action = self.db.get_action(game_id, action_id)
            return self._narrate_or_pending(action)

    def _narrate_or_pending(self, action: dict) -> dict:
        """叙事失败时返回待重试状态，已提交事实保持不变。"""
        if action["status"] == "complete":
            return self._response(action)
        # 上下文每回合从已提交事实重建，不保留跨场景的模型记忆。
        events = self.db.get_events(action["game_id"])
        case_state = self.db.get_case_state(action["game_id"])
        knowledge = self.db.get_player_knowledge(action["game_id"])
        bundle = case_for_game(self.db, action["game_id"])
        action_content = None
        if action["intent"].get("kind") == "case_action":
            action_content = action_by_id(action["intent"]["action_id"], bundle)
        context = trim_context(
            build_narrative_context(events, case_state, knowledge, action, bundle)
        )["context"]
        previous = previous_narrative_texts(events, limit=2)
        try:
            narrative = self.model.narrate(
                action["intent"],
                action["roll"],
                context=context,
                previous_narratives=previous,
                action_content=action_content,
            )
        except SimulationError:
            return self._with_case(self.db._pending_response(action), action["game_id"])
        completed = self.db.complete_action(action["game_id"], action["id"], narrative)
        return self._with_case(completed, action["game_id"])

    def _response(self, action: dict) -> dict:
        """返回已完成响应或当前待叙事响应。"""
        if action["status"] == "complete":
            response = json.loads(action["response_json"])
        else:
            response = self.db._pending_response(action)
        return self._with_case(response, action["game_id"])

    def _with_case(self, response: dict, game_id: str) -> dict:
        """附带当前案件公开状态，方便前端刷新地点、线索、时钟和版本。"""
        case_state = self.db.get_case_state(game_id)
        bundle = case_for_game(self.db, game_id)
        return {
            **response,
            "case": public_state(case_state, self.db.get_local_plans(game_id), bundle),
        }
