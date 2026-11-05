"""程序说明：以纯函数判断NPC回应，并计算获准的社交状态、履历与计划。"""


def judge_social_response(action, outcome, social_states, local_plans):
    """先判断NPC如何回应，再决定是否允许固定社交效果生效。"""
    if action["id"] != "reassure_fangsheng":
        return None
    if outcome != "no_roll":
        return {
            "response_id": "fangsheng_evaded",
            "response_kind": "evade",
            "reason_codes": ["outcome_not_applicable"],
            "public_text_key": "fangsheng_evaded_response",
            "allow_social_effects": False,
        }
    has_commission = any(
        item.get("state_id") == "fang_sheng:player:relationship"
        and item.get("value_text") == "委托人"
        and item.get("status") == "active"
        for item in social_states
    )
    if not has_commission:
        return {
            "response_id": "fangsheng_refused",
            "response_kind": "refuse",
            "reason_codes": ["valid_commission_missing"],
            "public_text_key": "fangsheng_refused_response",
            "allow_social_effects": False,
        }
    repeated = any(
        item.get("state_id") == "fang_sheng:player:trust" for item in social_states
    ) or any(item.get("plan_id") == "fangsheng_followup" for item in local_plans)
    if repeated:
        return {
            "response_id": "fangsheng_already_reassured",
            "response_kind": "conditional",
            "reason_codes": ["safety_promise_already_recorded"],
            "public_text_key": "fangsheng_already_reassured_response",
            "allow_social_effects": False,
        }
    return {
        "response_id": "fangsheng_reassured",
        "response_kind": "accept",
        "reason_codes": ["valid_commission", "safety_promise"],
        "public_text_key": "fangsheng_reassured_response",
        "allow_social_effects": True,
    }


def build_social_changes(
    action: dict,
    outcome: str,
    after_time: int,
    social_states: list[dict],
    local_plans: list[dict],
    response: dict | None = None,
) -> dict:
    """只展开回应者允许的固定社交声明；重复安抚不会叠加效果。"""
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
    response = response or judge_social_response(
        action, outcome, social_states, local_plans
    )
    if not response["allow_social_effects"]:
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
