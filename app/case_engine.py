"""程序说明：提供 C01 案件的初始状态、可用行动和确定性状态转换。"""

import copy

from app.case_content import ACTIONS, CLUE_LABELS, ENDINGS, LOCATIONS


def initial_state() -> dict:
    """返回每个新存档共享的 C01 初始状态。"""
    return {
        "phase": "unoffered",
        "location": "OC-01",
        "clock": 0,
        "world_time": 0,
        "clues": [],
        "ending": None,
        "revision": 0,
    }


def get_location(location_id: str) -> dict:
    """返回地点显示信息，未知地点由调用层显式处理。"""
    return LOCATIONS[location_id]


def available_actions(state: dict) -> list[dict]:
    """根据当前地点、阶段和线索，返回玩家可见且合法的行动。"""
    result = []
    for action in ACTIONS:
        if not _phase_matches(action, state):
            continue
        if not _location_matches(action, state):
            continue
        if not _clues_met(action, state):
            continue
        result.append(action)
    return result


def resolve_action(state: dict, action: dict, roll_outcome: str | None) -> dict:
    """按固定行动效果推进案件状态；模型只负责文字，不能修改此处结果。"""
    next_state = copy.deepcopy(state)
    outcome = roll_outcome or "no_roll"
    effect = action["effects"].get(outcome, {})

    for clue in effect.get("clues_add", []):
        if clue not in next_state["clues"]:
            next_state["clues"].append(clue)

    next_state["clock"] += effect.get("clock_add", 0)
    next_state["world_time"] = next_state.get("world_time", 0) + action.get("time_cost", 0)
    if "location_to" in effect:
        next_state["location"] = effect["location_to"]
    if "phase_to" in effect:
        next_state["phase"] = effect["phase_to"]
    if "ending" in effect:
        next_state["ending"] = effect["ending"]
    return next_state


def action_by_id(action_id: str) -> dict:
    """按固定行动编号读取内容，避免服务层到处重复定义行动。"""
    for action in ACTIONS:
        if action["id"] == action_id:
            return action
    raise KeyError("案件行动不存在")


def public_state(state: dict, plans: list[dict] | None = None) -> dict:
    """返回公开案件状态、时间和计划，不包含任何私密社会状态。"""
    return {
        "phase": state["phase"],
        "location": state["location"],
        "location_name": LOCATIONS[state["location"]]["name"],
        "district": LOCATIONS[state["location"]]["district"],
        "clock": state["clock"],
        "clock_max": 4,
        "world_time": state.get("world_time", 0),
        "plans": [
            {
                "plan_id": plan["plan_id"],
                "holder_id": plan["holder_id"],
                "due_time": plan["due_time"],
                "status": plan["status"],
            }
            for plan in (plans or [])
        ],
        "clues": [{"id": clue, "label": CLUE_LABELS[clue]} for clue in state["clues"]],
        "ending": ENDINGS.get(state["ending"]) if state["ending"] else None,
        "revision": state.get("revision", 0),
        "actions": [
            {"id": action["id"], "label": action["label"]}
            for action in available_actions(state)
        ],
    }


def _phase_matches(action: dict, state: dict) -> bool:
    return state["phase"] in action["phases"]


def _location_matches(action: dict, state: dict) -> bool:
    if action["location"] == "*":
        return True
    return action["location"] == state["location"]


def _clues_met(action: dict, state: dict) -> bool:
    clues = set(state["clues"])
    if not all(clue in clues for clue in action.get("requires_clues", [])):
        return False
    any_clues = action.get("requires_clues_any", [])
    if any_clues and not any(clue in clues for clue in any_clues):
        return False
    return True
