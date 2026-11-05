"""程序说明：以纯函数构建NPC自身知识视图、评分候选并安全试算固定效果。"""

from copy import deepcopy
import hashlib
import json

from app.action_protocol import RULES_VERSION
from app.cognition_engine import (
    PRECISION_RANK,
    build_cognition_view,
)
from app.case_content import (
    AUTONOMY_EFFECT_DEFINITIONS,
    AUTONOMY_PLAN_DEFINITIONS,
    CONTENT_VERSION,
    NPC_INITIAL_KNOWLEDGE,
)


EMPTY_CHANGES = {
    "plans": [], "states": [], "knowledge": [], "history": [], "public": [],
}


def build_npc_knowledge(holder_id, knowledge_records, public_facts=()):
    """只合并固定初始知识和本人认知；公开事实不自动成为精确记忆。"""
    refs = set(NPC_INITIAL_KNOWLEDGE.get(holder_id, []))
    for record in knowledge_records:
        if record.get("holder_id") != holder_id:
            continue
        ref = record.get("knowledge_id") or record.get("id") or record.get("fact_id")
        if ref:
            refs.add(ref)
    return sorted(refs)


def _find_knowledge(view, reference):
    """按固定语义编号查找新档记录，同时兼容纯函数旧测试编号。"""
    return next(
        (
            item for item in view
            if item["knowledge_id"] == reference
            or item["knowledge_id"].endswith(f":{reference}")
        ),
        None,
    )


def make_decision_context(
    case_state,
    social_states,
    local_plans,
    knowledge,
    character_history,
    events,
    roll_count,
):
    """提取并发复核所需的规范输入，排除物理编号、时间戳和叙事文本。"""
    case_keys = ("phase", "location", "clock", "world_time", "clues", "ending", "revision")
    social_keys = (
        "state_id", "holder_id", "target_id", "kind", "value_int", "value_text",
        "visibility", "starts_at", "expires_at", "status",
    )
    plan_keys = ("plan_id", "holder_id", "scope", "due_time", "status")
    knowledge_keys = (
        "holder_id", "kind", "fact_id", "content", "accuracy", "visibility",
        "source_record_id", "observed_at", "precision", "corrects_record_id",
    )
    history_keys = ("holder_id", "kind", "content", "structured", "visibility")
    scenes = []
    for event in events:
        if event.get("kind") != "scene_activated":
            continue
        payload = event.get("payload") or json.loads(event["payload_json"])
        scenes.append({
            key: payload.get(key)
            for key in ("scene_id", "plan_id", "holder_id", "candidate_id")
        })
    return {
        "case": {
            key: (sorted(case_state.get(key, [])) if key == "clues" else case_state.get(key))
            for key in case_keys
        },
        "social_states": [
            {key: item.get(key) for key in social_keys} for item in social_states
        ],
        "local_plans": [{key: item.get(key) for key in plan_keys} for item in local_plans],
        "knowledge": [
            {
                "knowledge_id": item.get("knowledge_id") or item.get("id"),
                **{key: item.get(key) for key in knowledge_keys},
            }
            for item in knowledge
        ],
        "character_history": [
            {key: item.get(key) for key in history_keys} for item in character_history
        ],
        "activated_scenes": scenes,
        "roll_count": roll_count,
        "world_time": case_state.get("world_time", 0),
        "rules_version": RULES_VERSION,
        "content_version": CONTENT_VERSION,
    }


def decision_context_hash(context):
    """按规范JSON计算决策上下文指纹，供事务内重读复核。"""
    canonical = json.dumps(
        context, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def decide_npc_plan(
    plan,
    context,
    plan_definitions=None,
    effect_definitions=None,
):
    """逐项检查知识、关系、记忆和固定效果，在深拷贝上试算后选择候选。"""
    working = deepcopy(context)
    current_plan = deepcopy(plan)
    definitions = plan_definitions or AUTONOMY_PLAN_DEFINITIONS
    effects = effect_definitions or AUTONOMY_EFFECT_DEFINITIONS
    definition = definitions.get(current_plan["plan_id"])
    if definition is None:
        raise ValueError("到期计划缺少自主候选定义")
    candidates = definition.get("candidates", [])
    if len(candidates) > 8:
        raise ValueError("单个计划的自主候选超过8项上限")

    holder_id = current_plan["holder_id"]
    knowledge_refs = build_npc_knowledge(
        holder_id, working.get("knowledge", []), working.get("public_facts", [])
    )
    knowledge = set(knowledge_refs)
    current_rules = working.get("rules_version") == RULES_VERSION
    after_time = working.get(
        "after_time", working.get("case", {}).get("world_time", 0)
    )
    cognition_view = build_cognition_view(
        holder_id, working.get("knowledge", []), after_time
    ) if current_rules else None
    trust = _active_trust(holder_id, working.get("social_states", []))
    has_promise = _has_promise(holder_id, working.get("character_history", []))
    audited = []
    eligible = []
    for candidate in candidates:
        candidate_id = candidate.get("candidate_id")
        reasons = []
        missing = sorted(set(candidate.get("requires_knowledge", [])) - knowledge)
        if missing:
            reasons.append("missing_knowledge")
        if cognition_view is not None:
            for reference, minimum in candidate.get("min_precision", {}).items():
                record = _find_knowledge(cognition_view, reference)
                actual = record["effective_precision"] if record else "unknown"
                if PRECISION_RANK[actual] < PRECISION_RANK[minimum]:
                    reasons.append("insufficient_precision")
        if trust < candidate.get("min_trust", -2):
            reasons.append("insufficient_trust")
        required_memory = candidate.get("requires_memory")
        if required_memory and not _has_promise(
            holder_id, working.get("character_history", []), required_memory
        ):
            reasons.append("missing_memory")
        effect = effects.get(candidate.get("effect_id"))
        if effect is None:
            reasons.append("unknown_effect")
        else:
            try:
                changes = _trial_effect(
                    effect, current_plan, cognition_view, after_time
                )
            except (TypeError, ValueError, KeyError):
                reasons.append("unsafe_effect")
        score = {
            "goal": candidate.get("score", {}).get("goal", 0),
            "knowledge": candidate.get("score", {}).get("knowledge", 0),
            "relationship": trust,
            "memory": 2 if has_promise else 0,
            "risk": candidate.get("score", {}).get("risk", 0),
        }
        score["total"] = sum(score.values())
        audited.append({
            "candidate_id": candidate_id,
            "eligible": not reasons,
            "excluded_reasons": reasons,
            "score": score,
        })
        if not reasons:
            eligible.append((candidate, changes))

    # 总分降序、编号升序决胜；任何阶段都不消耗随机数。
    score_by_id = {item["candidate_id"]: item["score"]["total"] for item in audited}
    eligible.sort(key=lambda item: (
        -score_by_id[item[0]["candidate_id"]], item[0]["candidate_id"]
    ))
    if eligible:
        selected, changes = eligible[0]
        selected_id = selected["candidate_id"]
        reasons = list(selected.get("selection_reason_codes", []))
    else:
        selected_id = None
        changes = deepcopy(EMPTY_CHANGES)
        reasons = ["no_eligible_candidate"]
    return {
        "plan_id": current_plan["plan_id"],
        "holder_id": holder_id,
        "knowledge_refs": knowledge_refs,
        "candidates": audited,
        "selected_candidate_id": selected_id,
        "selection_reason_codes": reasons,
        "changes": changes,
    }


def _active_trust(holder_id, states):
    """读取NPC对玩家的有界信任；缺失时按中立0处理。"""
    return next((
        item.get("value_int", 0) for item in states
        if item.get("holder_id") == holder_id
        and item.get("target_id") == "player"
        and item.get("kind") == "trust"
        and item.get("status") == "active"
    ), 0)


def _has_promise(holder_id, history, promise="优先确认苗雨安全"):
    """只读取该NPC自己的社会记忆，不使用玩家假设或他人记忆。"""
    return any(
        item.get("holder_id") == holder_id
        and item.get("kind") == "social_memory"
        and (
            (item.get("structured") or {}).get("promise") == promise
            or promise in item.get("content", "")
        )
        for item in history
    )


def _trial_effect(effect, plan, cognition_view=None, after_time=0):
    """校验固定效果形状并生成试算变化；禁止任意字段和越权产物。"""
    allowed = {
        "complete_plan", "testimony", "history", "public",
        "knowledge_source", "correction_id",
    }
    if not isinstance(effect, dict) or set(effect) - allowed:
        raise ValueError("自主效果包含未声明字段")
    if type(effect.get("complete_plan")) is not bool:
        raise ValueError("自主效果缺少合法计划完成标记")
    changes = deepcopy(EMPTY_CHANGES)
    if not effect["complete_plan"]:
        if set(effect) != {"complete_plan"}:
            raise ValueError("等待效果不能附带世界变化")
        return changes

    testimony = effect["testimony"]
    required = {"holder_id", "kind", "fact_id", "content", "accuracy", "visibility"}
    if set(testimony) != required or testimony["holder_id"] != plan["holder_id"]:
        raise ValueError("自主证词字段或持有者越权")
    if testimony["kind"] != "testimony" or testimony["visibility"] not in {"player", "public"}:
        raise ValueError("自主证词类型或可见性非法")
    spoken = deepcopy(testimony)
    source = None
    if effect.get("knowledge_source") and cognition_view is not None:
        source = _find_knowledge(cognition_view, effect["knowledge_source"])
        if source is None:
            raise ValueError("自主证词缺少本人认知来源")
        spoken.update({
            "source_record_id": source["knowledge_id"],
            "observed_at": None,
            "precision": source["effective_precision"],
            "corrects_record_id": None,
        })
    changes["plans"].append({"plan_id": plan["plan_id"], "status": "completed"})
    changes["knowledge"].append(spoken)
    if effect.get("correction_id") and source is not None:
        inference = _find_knowledge(
            cognition_view, "fang_sheng:last_login_inference"
        )
        if inference is not None and not inference["corrected_by"]:
            changes["knowledge"].append({
                "holder_id": plan["holder_id"],
                "kind": "memory",
                "fact_id": None,
                "content": "方笙重新核对排班：最后登录不足以证明当晚只有邵谦使用凭证。",
                "accuracy": "honest",
                "visibility": "private",
                "source_record_id": source["knowledge_id"],
                "observed_at": after_time,
                "precision": "exact",
                "corrects_record_id": inference["knowledge_id"],
                "reason_codes": ["old_schedule_rechecked", "overgeneralization_retracted"],
            })
        public_target = next(
            (
                item for item in cognition_view
                if item["kind"] == "testimony"
                and item["visibility"] == "player"
                and inference is not None
                and item.get("source_record_id") == inference["knowledge_id"]
                and not item["corrected_by"]
            ),
            None,
        )
        if public_target is not None:
            changes["knowledge"].append({
                "holder_id": plan["holder_id"],
                "kind": "testimony",
                "fact_id": None,
                "content": "方笙纠正：最后登录不足以证明当晚只有邵谦使用凭证。",
                "accuracy": "honest",
                "visibility": "player",
                "source_record_id": source["knowledge_id"],
                "observed_at": None,
                "precision": source["effective_precision"],
                "corrects_record_id": public_target["knowledge_id"],
                "reason_codes": ["old_schedule_rechecked", "overgeneralization_retracted"],
            })
    changes["history"].append({
        "holder_id": plan["holder_id"],
        "kind": "plan",
        "content": effect["history"],
        "structured": {
            "plan_id": plan["plan_id"],
            "before": {"status": "pending"},
            "after": {"status": "completed"},
        },
        "visibility": "public",
    })
    changes["public"].append(effect["public"])
    return changes
