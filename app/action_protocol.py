"""程序说明：定义行动宿主命令、规范化请求哈希和管线异常边界。"""

import hashlib
import json


RULES_VERSION = "action-pipeline-1.0"
MESSAGE_KINDS = (
    "visible_expression",
    "action_intent",
    "response_judgment",
    "fact_proposal",
    "host_command",
    "narrative_report",
)


class ActionConflict(RuntimeError):
    """行动冲突基类，由接口层统一映射为 409。"""


class IdempotencyConflict(ActionConflict):
    """同一请求标识承载了不同命令内容。"""


class StateConflict(ActionConflict):
    """提交时状态版本或随机序号已经变化。"""


class PermissionDenied(RuntimeError):
    """事实提案未通过对应作用域的程序审核。"""


def normalize_text(text: str) -> str:
    """统一空白，确保同一命令得到稳定哈希。"""
    return " ".join(text.split())


def make_command(
    text: str,
    action_id: str | None = None,
    expected_revision: int | None = None,
) -> dict:
    """构造服务端允许的宿主命令；kind 不接受客户端任意指定。"""
    return {
        "kind": "action.submit",
        "text": normalize_text(text),
        "action_id": action_id,
        "expected_revision": expected_revision,
    }


def make_request_hash(game_id: str, command: dict) -> str:
    """按游戏和完整命令计算幂等指纹。"""
    canonical = json.dumps(
        {"game_id": game_id, **command},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
