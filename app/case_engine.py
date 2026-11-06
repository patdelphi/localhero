"""程序说明：提供案件的初始状态、可用行动和确定性状态转换。

默认案件为 C01；调用方可通过 case 参数切换到其他已注册案件。
"""

import copy

from app.case_registry import CaseBundle, default_case


def initial_state(case: CaseBundle | None = None) -> dict:
    """返回指定案件的初始状态，未传案件时保持 C01 旧行为。"""
    bundle = case or default_case()
    return {
        "phase": bundle.start_phase,
        "location": bundle.start_location,
        "clock": 0,
        "world_time": 0,
        "clues": [],
        "ending": None,
        "revision": 0,
    }


def get_location(location_id: str, case: CaseBundle | None = None) -> dict:
    """返回地点显示信息，未知地点由调用层显式处理。"""
    bundle = case or default_case()
    return bundle.locations[location_id]


def available_actions(state: dict, case: CaseBundle | None = None) -> list[dict]:
    """根据当前地点、阶段和线索，返回玩家可见且合法的行动。"""
    bundle = case or default_case()
    result = []
    for action in bundle.actions:
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


def action_by_id(action_id: str, case: CaseBundle | None = None) -> dict:
    """按固定行动编号读取内容，未知编号抛 KeyError。"""
    bundle = case or default_case()
    return bundle.action(action_id)


def public_state(
    state: dict,
    plans: list[dict] | None = None,
    case: CaseBundle | None = None,
) -> dict:
    """返回公开案件状态、时间和计划，不包含任何私密社会状态。"""
    bundle = case or default_case()
    clues = []
    for clue in state["clues"]:
        item = {"id": clue, "label": bundle.clue_labels[clue]}
        # 跨案线索携带关联案件元数据，前端据此显示标记。
        if clue in bundle.cross_case_links:
            item["cross_case"] = bundle.cross_case_links[clue]
        clues.append(item)
    return {
        "case_id": bundle.case_id,
        "case_title": bundle.title,
        "phase": state["phase"],
        "location": state["location"],
        "location_name": bundle.locations[state["location"]]["name"],
        "district": bundle.locations[state["location"]]["district"],
        "clock": state["clock"],
        "clock_max": bundle.clock_max,
        "clock_label": bundle.clock_label,
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
        "clues": clues,
        "ending": bundle.endings.get(state["ending"]) if state["ending"] else None,
        "revision": state.get("revision", 0),
        "actions": [
            {"id": action["id"], "label": action["label"]}
            for action in available_actions(state, bundle)
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
