"""程序说明：以纯函数推进 C01 固定计划到期和短期社会状态结束。"""

from app.case_content import LOCAL_PLAN_DEFINITIONS


def advance_local_simulation(
    after_time: int,
    social_states: list[dict],
    local_plans: list[dict],
) -> dict:
    """仅处理当前行动中已经到期的固定事项，顺序完全确定。"""
    result = {
        "plans": [],
        "states": [],
        "knowledge": [],
        "history": [],
        "public": [],
    }
    due_plans = sorted(
        (
            item for item in local_plans
            if item["scope"] == "c01"
            and item["status"] == "pending"
            and item["due_time"] <= after_time
        ),
        key=lambda item: (item["due_time"], item["plan_id"]),
    )
    for plan in due_plans:
        definition = LOCAL_PLAN_DEFINITIONS.get(plan["plan_id"])
        if definition is None:
            raise ValueError("到期计划缺少固定内容定义")
        result["plans"].append({"plan_id": plan["plan_id"], "status": "completed"})
        result["knowledge"].append(dict(definition["testimony"]))
        result["history"].append({
            "holder_id": plan["holder_id"],
            "kind": "plan",
            "content": definition["history"],
            "structured": {
                "plan_id": plan["plan_id"],
                "before": {"status": "pending"},
                "after": {"status": "completed"},
            },
            "visibility": "public",
        })
        result["public"].append(definition["history"])

    ended_states = sorted(
        (
            item for item in social_states
            if item["kind"] == "condition"
            and item["status"] == "active"
            and item["expires_at"] is not None
            and item["expires_at"] <= after_time
        ),
        key=lambda item: item["state_id"],
    )
    for state in ended_states:
        result["states"].append({"state_id": state["state_id"], "status": "ended"})
        content = f"{state['holder_id']}的短期状态“{state['value_text']}”已结束。"
        # 固定人物标识转成玩家熟悉的展示名。
        content = content.replace("fang_sheng", "方笙")
        result["history"].append({
            "holder_id": state["holder_id"],
            "kind": "condition",
            "content": content,
            "structured": {
                "state_id": state["state_id"],
                "before": {"status": "active"},
                "after": {"status": "ended"},
            },
            "visibility": state["visibility"],
        })
        if state["visibility"] in {"public", "player"}:
            result["public"].append(content)
    return result
