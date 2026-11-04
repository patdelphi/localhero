"""程序说明：以纯函数计算 C01 固定行动产生的社会状态、同源履历与计划。"""


def build_social_changes(
    action: dict,
    outcome: str,
    after_time: int,
    social_states: list[dict],
    local_plans: list[dict],
) -> dict:
    """只展开固定社交声明；重复安抚不会叠加信任、记忆或计划。"""
    empty = {"states": [], "history": [], "plans": [], "public": []}
    if outcome != "no_roll":
        return empty

    state_ids = {item["state_id"] for item in social_states}
    if action["id"] == "accept_commission":
        state_id = "fang_sheng:player:relationship"
        if state_id in state_ids:
            return empty
        state = {
            "state_id": state_id,
            "holder_id": "fang_sheng",
            "target_id": "player",
            "kind": "relationship",
            "value_int": None,
            "value_text": "委托人",
            "visibility": "public",
            "starts_at": after_time,
            "expires_at": None,
            "status": "active",
        }
        return {
            "states": [state],
            "history": [{
                "holder_id": "fang_sheng",
                "kind": "relationship",
                "content": "方笙成为你的委托人。",
                "structured": {
                    "state_id": state_id,
                    "before": None,
                    "after": {"value_text": "委托人", "status": "active"},
                },
                "visibility": "public",
            }],
            "plans": [],
            "public": ["方笙成为你的委托人。"],
        }

    if action["id"] != "reassure_fangsheng":
        return empty
    trust_id = "fang_sheng:player:trust"
    condition_id = "fang_sheng:condition:reassured"
    plan_id = "fangsheng_followup"
    # 任一核心投影已经存在，都说明该固定社交链已经提交过。
    if trust_id in state_ids or any(item["plan_id"] == plan_id for item in local_plans):
        return empty

    trust = {
        "state_id": trust_id,
        "holder_id": "fang_sheng",
        "target_id": "player",
        "kind": "trust",
        "value_int": 1,
        "value_text": None,
        "visibility": "private",
        "starts_at": after_time,
        "expires_at": None,
        "status": "active",
    }
    condition = {
        "state_id": condition_id,
        "holder_id": "fang_sheng",
        "target_id": None,
        "kind": "condition",
        "value_int": None,
        "value_text": "态度缓和",
        "visibility": "public",
        "starts_at": after_time,
        "expires_at": after_time + 3,
        "status": "active",
    }
    plan = {
        "plan_id": plan_id,
        "holder_id": "fang_sheng",
        "scope": "c01",
        "due_time": after_time + 2,
        "status": "pending",
    }
    history = [
        {
            "holder_id": "fang_sheng",
            "kind": "trust",
            "content": "方笙对你的信任有所提升。",
            "structured": {
                "state_id": trust_id,
                "before": {"value_int": 0},
                "after": {"value_int": 1},
            },
            "visibility": "private",
        },
        {
            "holder_id": "fang_sheng",
            "kind": "condition",
            "content": "方笙的态度缓和了。",
            "structured": {
                "state_id": condition_id,
                "before": None,
                "after": {"status": "active", "expires_at": after_time + 3},
            },
            "visibility": "public",
        },
        {
            "holder_id": "fang_sheng",
            "kind": "social_memory",
            "content": "方笙记得：你承诺优先确认苗雨安全。",
            "structured": {"state_id": trust_id, "promise": "优先确认苗雨安全"},
            "visibility": "private",
        },
        {
            "holder_id": "fang_sheng",
            "kind": "plan",
            "content": "方笙将整理旧排班补充。",
            "structured": {
                "plan_id": plan_id,
                "before": None,
                "after": {"status": "pending", "due_time": after_time + 2},
            },
            "visibility": "public",
        },
    ]
    return {
        "states": [trust, condition],
        "history": history,
        "plans": [plan],
        "public": ["方笙的态度缓和了。", "方笙将整理旧排班补充。"],
    }
