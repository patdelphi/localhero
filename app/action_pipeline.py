"""程序说明：实现候选过滤、Before/Instead/Check、权限审核和有界 After 规划。"""

from app.action_protocol import PermissionDenied, RULES_VERSION
from app.case_content import (
    ACTIONS,
    ACTION_METADATA,
    CLUE_LABELS,
    CONTENT_VERSION,
    KNOWLEDGE_DECLARATIONS,
)
from app.case_engine import action_by_id, resolve_action


class CaseAuthorizer:
    """独立审核事实作用域；模型或发起者不能自行授予权限。"""

    def authorize(self, fact_proposal: dict, state: dict | None = None) -> dict:
        """只允许场景和固定案件提案，全球正典必须人工批准。"""
        scope = fact_proposal.get("scope")
        if scope == "global_canon":
            raise PermissionDenied("全球正典只能经人工批准后修改")
        if scope == "case":
            if state is None or fact_proposal.get("object") not in {
                action["id"] for action in ACTIONS
            }:
                raise PermissionDenied("案件事实缺少固定内容或状态依据")
            return {
                "allowed": True,
                "fact_level": "case",
                "reason": "固定 C01 内容与前置条件审核通过",
            }
        if scope == "scene":
            return {
                "allowed": True,
                "fact_level": "scene",
                "reason": "仅提交本次行动，不改写案件或全球正典",
            }
        raise PermissionDenied("未知事实作用域，不能自动提交")


def candidate_actions(state: dict) -> list[dict]:
    """列出固定候选及逐项排除理由，供预览和审计共同使用。"""
    result = []
    clues = set(state["clues"])
    for action in ACTIONS:
        reasons = []
        if state["phase"] not in action["phases"]:
            reasons.append("当前案件阶段不可用")
        if action["location"] not in ("*", state["location"]):
            reasons.append("当前地点不可用")
        missing = [clue for clue in action.get("requires_clues", []) if clue not in clues]
        if missing:
            reasons.append(f"缺少前置线索：{', '.join(missing)}")
        any_clues = action.get("requires_clues_any", [])
        if any_clues and not any(clue in clues for clue in any_clues):
            reasons.append(f"缺少任一前置线索：{', '.join(any_clues)}")
        result.append(
            {
                "action_id": action["id"],
                "label": action["label"],
                "eligible": not reasons,
                "excluded_reasons": reasons,
            }
        )
    return result


def prepare_action(
    text: str,
    state: dict,
    model,
    action_id: str | None = None,
) -> dict:
    """生成不写库、不掷骰的行动计划，显式选择也必须通过 Check。"""
    candidates = candidate_actions(state)
    by_id = {candidate["action_id"]: candidate for candidate in candidates}

    if action_id is not None:
        if action_id not in by_id:
            raise PermissionDenied("宿主命令指定的行动不存在")
        action = action_by_id(action_id)
        intent = _case_intent(action)
        selected = by_id[action_id]
        selection_source = "host_command"
        selection_reason = "显式宿主命令选择替代计划"
    else:
        legal_actions = [
            action_by_id(candidate["action_id"])
            for candidate in candidates
            if candidate["eligible"]
        ]
        intent = model.parse_action(text, legal_actions)
        selection_source = "parsed_intent"
        selection_reason = "确定性意图解析选择"
        if intent["kind"] == "case_action":
            action_id = intent["action_id"]
            if action_id not in by_id:
                raise PermissionDenied("解析结果不是固定案件行动")
            action = action_by_id(action_id)
            selected = by_id[action_id]
        else:
            action = None
            selected = None

    eligible = selected["eligible"] if selected else True
    reason = None if eligible else "；".join(selected["excluded_reasons"])
    selected_id = action_id or intent["kind"]
    authorizer = CaseAuthorizer()
    permission = authorizer.authorize(
        {
            "scope": "case" if action else "scene",
            "object": selected_id,
            "effect": "resolve_action" if action else "action_only",
            "source_action": selected_id,
            "valid_when": "提交事务内状态版本与随机序号均未变化",
        },
        state,
    )
    if not eligible:
        permission = {
            "allowed": False,
            "fact_level": "case",
            "reason": reason,
        }

    pipeline = [
        {
            "stage": "Before",
            "rule_id": "before.filter_candidates",
            "result": "已按阶段、地点和前置线索过滤候选",
        },
        {
            "stage": "Instead",
            "rule_id": "instead.explicit_action" if selection_source == "host_command" else "instead.none",
            "result": selection_reason,
        },
        {
            "stage": "Check",
            "rule_id": "check.case_authorizer" if action else "check.scene_authorizer",
            "result": permission["reason"],
        },
        {
            "stage": "After",
            "rule_id": "after.bounded_reactions",
            "result": "无额外反应",
            "reactions": [],
        },
    ]
    return {
        "can_submit": eligible,
        "reason": reason,
        "intent": intent,
        "candidates": candidates,
        "selected_action": {
            "action_id": selected_id,
            "selection_source": selection_source,
            "selection_reason": selection_reason,
        },
        "declaration": make_declaration(intent, action, state),
        "mechanical_changes": preview_structured_changes(action, state),
        "pipeline": pipeline,
        "permission": permission,
        "case_action": action is not None,
    }


def make_declaration(intent: dict, action: dict | None, state: dict) -> dict:
    """生成掷骰前目标、处境、效果、代价与修正来源。"""
    if action is None:
        requires_roll = intent["requires_roll"]
        return {
            "target": f"{state['location']} 当前场景",
            "method": intent["tendency"],
            "position": "有风险，需要公开 2D6" if requires_roll else "平稳，无需掷骰",
            "effect": "记录本次场景行动，不改变固定案件事实",
            "cost": "可能承担一般局势代价" if requires_roll else "无机械代价",
            "modifier_source": "通用行动固定修正",
        }

    metadata = ACTION_METADATA.get(action["id"], {})
    effects = list(action["effects"].values())
    adds_clue = any(effect.get("clues_add") for effect in effects)
    changes_state = any(
        key in effect
        for effect in effects
        for key in ("location_to", "phase_to", "ending")
    )
    if "effect" in metadata:
        effect_text = metadata["effect"]
    elif adds_clue:
        effect_text = "按判定结果获得固定线索，核心线索不会被坏骰永久删除"
    elif changes_state:
        effect_text = "推进固定地点、案件阶段或结局"
    else:
        effect_text = "获得信息，不改变案件机械状态"
    has_clock_cost = any(effect.get("clock_add", 0) for effect in effects)
    return {
        "target": metadata.get("target", action["label"]),
        "method": action["tendency"],
        "position": "有风险，需要公开 2D6" if action["requires_roll"] else "平稳，无需掷骰",
        "effect": effect_text,
        "cost": "可能推进项目清理时钟" if has_clock_cost else "无机械代价",
        "modifier_source": metadata.get("modifier_source", "C01 固定行动修正"),
    }


def preview_structured_changes(action: dict | None, state: dict) -> list[dict]:
    """按判定结果列出预览摘要；此处不分配来源事件或写入数据库。"""
    if action is None:
        return []
    return [
        {"outcome": outcome, **build_structured_changes(action, state, outcome)}
        for outcome in action["effects"]
    ]


def build_structured_changes(action: dict, state: dict, outcome: str) -> dict:
    """从固定内容计算本次实际事实、Clock 与认知变化。"""
    effect = action["effects"].get(outcome, {})
    new_clues = [clue for clue in effect.get("clues_add", []) if clue not in state["clues"]]
    facts = [
        {
            "fact_id": clue,
            "subject_id": "C01",
            "fact_kind": "clue",
            "visibility": "player",
            "mechanical": {"grants_action_permission": True},
        }
        for clue in new_clues
    ]
    knowledge = [
        {
            "holder_id": "player",
            "kind": "observation",
            "fact_id": clue,
            "content": CLUE_LABELS[clue],
            "accuracy": "direct",
            "visibility": "player",
        }
        for clue in new_clues
    ]
    for declaration in KNOWLEDGE_DECLARATIONS.get(action["id"], []):
        if outcome in declaration["outcomes"]:
            knowledge.append(
                {key: value for key, value in declaration.items() if key != "outcomes"}
            )
    delta = effect.get("clock_add", 0)
    clock = None
    if delta:
        clock = {
            "clock_id": "project_cleanup",
            "reason": f"{action['id']}:{outcome}",
            "delta": delta,
            "before_value": state["clock"],
            "after_value": state["clock"] + delta,
        }
    return {"facts_add": facts, "clock": clock, "knowledge": knowledge}


def apply_plan(plan: dict, state: dict, roll: dict | None) -> dict | None:
    """纯计算主结果；没有案件变化时返回 None，After 不另造行动。"""
    if not plan["case_action"]:
        return None
    action = action_by_id(plan["intent"]["action_id"])
    next_state = resolve_action(state, action, roll["outcome"] if roll else None)
    keys = ("phase", "location", "clock", "clues", "ending")
    if all(next_state[key] == state[key] for key in keys):
        return None
    return next_state


def make_audit(
    plan: dict,
    game: dict,
    state: dict,
    roll: dict | None,
    next_state: dict | None,
    structured_changes: dict | None = None,
) -> dict:
    """把计划、权限和已发生的纯判定组成可持久化审计。"""
    after_revision = state["revision"] + (1 if next_state else 0)
    random_audit = None
    if roll:
        random_audit = {
            "seed": game["seed"],
            "sequence": game["roll_count"],
            **roll,
        }
    return {
        "audit_version": 1,
        "rules_version": RULES_VERSION,
        "content_version": CONTENT_VERSION,
        "candidates": plan["candidates"],
        "selected_action": plan["selected_action"],
        "pipeline": plan["pipeline"],
        "declaration": plan["declaration"],
        "structured_changes": structured_changes,
        "permission": plan["permission"],
        "random": random_audit,
        "state_revision": {"before": state["revision"], "after": after_revision},
        "status": "narrative_pending",
    }


def _case_intent(action: dict) -> dict:
    """由固定内容构造意图，显式命令不依赖模型补充字段。"""
    return {
        "kind": "case_action",
        "action_id": action["id"],
        "label": action["label"],
        "tendency": action["tendency"],
        "requires_roll": action["requires_roll"],
        "modifier": action["modifier"],
    }
