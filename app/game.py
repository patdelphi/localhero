"""程序说明：串行编排行动预览、程序判定、事务提交、审计和可重试叙事。"""

import json
import threading

from app.action_pipeline import apply_plan, make_audit, prepare_action
from app.action_protocol import (
    IdempotencyConflict,
    PermissionDenied,
    RULES_VERSION,
    StateConflict,
    make_command,
    make_request_hash,
    normalize_text,
)
from app.case_content import CONTENT_VERSION
from app.case_engine import public_state
from app.model import SimulationError
from app.rules import roll_for_sequence
from app.store import Database


class GameService:
    """掌握行动顺序；模拟模型只提供意图和文字，不掌握游戏事实。"""

    def __init__(self, database: Database, model):
        self.db = database
        self.model = model
        self._lock = threading.RLock()

    def create_game(self, protagonist: str) -> dict:
        """创建一个新存档。"""
        name = protagonist.strip()
        if not name:
            raise ValueError("主人公姓名不能为空")
        return self.db.create_game(name)

    def get_game(self, game_id: str) -> dict:
        """返回存档、案件公开状态及其完整事件历史。"""
        game = self.db.get_game(game_id)
        case = self.db.get_case_state(game_id)
        return {
            "game": game,
            "case": public_state(case),
            "events": self.db.get_events(game_id),
        }

    def preview_action(
        self, game_id: str, text: str, action_id: str | None = None
    ) -> dict:
        """只读生成行动声明；不写库、不掷骰、不推进随机序号。"""
        action_text = normalize_text(text)
        if not action_text:
            raise ValueError("行动内容不能为空")
        with self._lock:
            self.db.get_game(game_id)
            case_state = self.db.get_case_state(game_id)
            plan = prepare_action(action_text, case_state, self.model, action_id)
            return {
                "revision": case_state["revision"],
                "rules_version": RULES_VERSION,
                "content_version": CONTENT_VERSION,
                "normalized_input": action_text,
                "selected_action": plan["selected_action"],
                "candidates": plan["candidates"],
                "declaration": plan["declaration"],
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
            case_state = self.db.get_case_state(game_id)
            # 先识别过期预览，避免状态变化后的权限重验掩盖真正的并发冲突。
            if (
                expected_revision is not None
                and case_state["revision"] != expected_revision
            ):
                raise StateConflict("案件状态已变化，请重新预览")
            plan = prepare_action(action_text, case_state, self.model, action_id)
            if not plan["can_submit"]:
                raise PermissionDenied(plan["reason"] or "行动未通过程序审核")

            roll = None
            if plan["intent"]["requires_roll"]:
                roll = roll_for_sequence(
                    game["seed"], game["roll_count"], plan["intent"]["modifier"]
                ).to_dict()
            next_case_state = apply_plan(plan, case_state, roll)
            audit = make_audit(plan, game, case_state, roll, next_case_state)
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
            )
            return self._narrate_or_pending(action)

    def get_audit(self, game_id: str, limit: int = 50) -> dict:
        """读取有界审计列表，不暴露额外写入口。"""
        self.db.get_game(game_id)
        return {"items": self.db.get_audit(game_id, limit)}

    def retry_narrative(self, game_id: str, action_id: str) -> dict:
        """只重试叙事，不重新解析、掷骰或推进行动事实。"""
        with self._lock:
            action = self.db.get_action(game_id, action_id)
            return self._narrate_or_pending(action)

    def _narrate_or_pending(self, action: dict) -> dict:
        """叙事失败时返回待重试状态，已提交事实保持不变。"""
        if action["status"] == "complete":
            return self._response(action)
        try:
            narrative = self.model.narrate(action["intent"], action["roll"])
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
        return {**response, "case": public_state(case_state)}
