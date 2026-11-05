"""程序说明：按固定定义过滤并选择有界场景，无合法场景时丢弃候选产物。"""

from copy import deepcopy

from app.action_protocol import RULES_VERSION
from app.case_content import CONTENT_VERSION, SCENE_DEFINITIONS
from app.cognition_engine import PRECISION_RANK, build_cognition_view
from app.npc_decision import EMPTY_CHANGES, _find_knowledge, build_npc_knowledge


def select_scene(decision, context, scene_definitions=None):
    """场景只决定固定呈现；没有合法场景时不完成计划、不产生证词。"""
    working = deepcopy(context)
    definitions = SCENE_DEFINITIONS if scene_definitions is None else scene_definitions
    if len(definitions) > 16:
        raise ValueError("场景导演候选超过16项上限")
    selected_candidate = decision.get("selected_candidate_id")
    activated = {
        item if isinstance(item, str) else item.get("scene_id")
        for item in working.get("activated_scenes", [])
    }
    knowledge = set(build_npc_knowledge(
        decision["holder_id"], working.get("knowledge", []), working.get("public_facts", [])
    ))
    cognition_view = None
    if working.get("rules_version") == RULES_VERSION:
        cognition_view = build_cognition_view(
            decision["holder_id"], working.get("knowledge", []),
            working.get("after_time", working.get("world_time", 0)),
        )
    audited = []
    legal = []
    for scene in definitions:
        reasons = []
        if scene.get("candidate_id") != selected_candidate:
            reasons.append("candidate_not_selected")
        if scene.get("plan_id") != decision.get("plan_id"):
            reasons.append("plan_mismatch")
        if not _plan_is_due(scene, working):
            reasons.append("plan_not_due")
        if not _has_relationship(scene, working):
            reasons.append("missing_relationship")
        if set(scene.get("requires_knowledge", [])) - knowledge:
            reasons.append("missing_knowledge")
        if cognition_view is not None:
            for reference, minimum in scene.get("min_precision", {}).items():
                record = _find_knowledge(cognition_view, reference)
                actual = record["effective_precision"] if record else "unknown"
                if PRECISION_RANK[actual] < PRECISION_RANK[minimum]:
                    reasons.append("insufficient_precision")
        if scene.get("channel") not in working.get("channels", []):
            reasons.append("missing_channel")
        if not scene.get("repeatable", False) and scene.get("scene_id") in activated:
            reasons.append("already_activated")
        if "effects" in scene or "mechanical_effects" in scene:
            raise ValueError("场景定义不能附加机械效果")
        audited.append({
            "scene_id": scene.get("scene_id"),
            "candidate_id": scene.get("candidate_id"),
            "eligible": not reasons,
            "excluded_reasons": reasons,
            "selected": False,
        })
        if not reasons:
            legal.append(scene)

    legal.sort(key=lambda item: (-item.get("priority", 0), item["scene_id"]))
    if not legal:
        return {"scene": None, "scenes": audited, "changes": deepcopy(EMPTY_CHANGES)}
    chosen = legal[0]
    next(item for item in audited if item["scene_id"] == chosen["scene_id"])["selected"] = True
    event = {
        "scene_id": chosen["scene_id"],
        "plan_id": decision["plan_id"],
        "holder_id": decision["holder_id"],
        "candidate_id": selected_candidate,
        "channel": chosen["channel"],
        "presentation_key": chosen["presentation_key"],
        "rules_version": RULES_VERSION,
        "content_version": CONTENT_VERSION,
    }
    return {
        "scene": event,
        "scenes": audited,
        "changes": deepcopy(decision["changes"]),
    }


def _plan_is_due(scene, context):
    """场景只能承接当前已经到期且仍待处理的固定计划。"""
    return any(
        plan.get("plan_id") == scene.get("plan_id")
        and plan.get("status") == "pending"
        and plan.get("due_time", 0) <= context.get("after_time", 0)
        for plan in context.get("local_plans", [])
    )


def _has_relationship(scene, context):
    """核对场景需要的公开关系，不从场景台词反推权限。"""
    required = scene.get("requires_relationship")
    if required is None:
        return True
    return any(
        state.get("kind") == "relationship"
        and state.get("value_text") == required
        and state.get("status") == "active"
        for state in context.get("social_states", [])
    )
