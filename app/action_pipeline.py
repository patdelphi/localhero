"""程序说明：实现行动管线、NPC回应、自主决策、场景导演和版本2审计。"""

from copy import deepcopy

from app.action_protocol import PermissionDenied, RULES_VERSION
from app.case_content import (
    ACTIONS,
    ACTION_METADATA,
    CLUE_LABELS,
    CONTENT_VERSION,
    KNOWLEDGE_DECLARATIONS,
)
from app.case_engine import action_by_id, resolve_action
from app.cognition_engine import (
    assign_cognition_ids,
    build_cognition_view,
    build_declared_cognition,
    validate_cognition_changes,
)
from app.local_simulation import advance_local_simulation
from app.npc_decision import decide_npc_plan, make_decision_context
from app.scene_director import select_scene
from app.social_engine import build_social_changes, judge_social_response


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
    social_states: list[dict] | None = None,
    local_plans: list[dict] | None = None,
    decision_context: dict | None = None,
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

    return _complete_plan(
        state, intent, action_id, action, selected, candidates,
        selection_source, selection_reason, social_states, local_plans,
        decision_context,
    )


def prepare_recorded_action(
    command: dict,
    intent: dict,
    state: dict,
    social_states: list[dict] | None = None,
    local_plans: list[dict] | None = None,
    decision_context: dict | None = None,
) -> dict:
    """仅按已保存命令和意图重建计划，不解析文本、不调用模型。"""
    candidates = candidate_actions(state)
    by_id = {candidate["action_id"]: candidate for candidate in candidates}
    action_id = command.get("action_id")
    if intent.get("kind") == "case_action":
        recorded_id = intent.get("action_id")
        if action_id is not None and action_id != recorded_id:
            raise PermissionDenied("已保存命令与案件意图不一致")
        action_id = recorded_id
        if action_id not in by_id:
            raise PermissionDenied("已记录行动不是固定案件行动")
        action = action_by_id(action_id)
        selected = by_id[action_id]
    else:
        if action_id is not None:
            raise PermissionDenied("场景行动不能携带案件行动编号")
        action = None
        selected = None
    return _complete_plan(
        state, intent, action_id, action, selected, candidates,
        "recorded_replay", "按已保存规范命令与意图重算",
        social_states, local_plans, decision_context,
    )


def _complete_plan(
    state: dict,
    intent: dict,
    action_id: str | None,
    action: dict | None,
    selected: dict | None,
    candidates: list[dict],
    selection_source: str,
    selection_reason: str,
    social_states: list[dict] | None,
    local_plans: list[dict] | None,
    decision_context: dict | None = None,
) -> dict:
    """共用候选、Check、声明和机械计划，确保实时行动与回放同规则。"""
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

    instead_rule = {
        "host_command": "instead.explicit_action",
        "recorded_replay": "instead.recorded_replay",
    }.get(selection_source, "instead.none")
    pipeline = [
        {
            "stage": "Before",
            "rule_id": "before.filter_candidates",
            "result": "已按阶段、地点和前置线索过滤候选",
        },
        {
            "stage": "Instead",
            "rule_id": instead_rule,
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
        "mechanical_changes": preview_structured_changes(
            action, state, social_states, local_plans, decision_context
        ),
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
    costs = []
    if has_clock_cost:
        costs.append("可能推进项目清理时钟")
    if action.get("time_cost", 0):
        costs.append(f"消耗 {action['time_cost']} 点游戏内时间")
    return {
        "target": metadata.get("target", action["label"]),
        "method": action["tendency"],
        "position": "有风险，需要公开 2D6" if action["requires_roll"] else "平稳，无需掷骰",
        "effect": effect_text,
        "cost": "；".join(costs) if costs else "无机械代价",
        "modifier_source": metadata.get("modifier_source", "C01 固定行动修正"),
    }


def preview_structured_changes(
    action: dict | None,
    state: dict,
    social_states: list[dict] | None = None,
    local_plans: list[dict] | None = None,
    decision_context: dict | None = None,
) -> list[dict]:
    """按判定结果列出公开摘要，不暴露评分、知识引用或未激活场景。"""
    if action is None:
        return []
    previews = []
    for outcome in action["effects"]:
        changes = build_structured_changes(
            action, state, outcome, social_states, local_plans, decision_context
        )
        after_time = changes["world_time"]["after"]
        has_due_plan = any(
            item["status"] == "pending" and item["due_time"] <= after_time
            for item in (local_plans or [])
        )
        changes["social"] = {"public": changes["social"]["public"]}
        changes["simulation"] = {
            "public": ["可能处理已到期公开计划。"] if has_due_plan else []
        }
        changes.pop("scenes", None)
        changes.pop("autonomy", None)
        previews.append({"outcome": outcome, **changes})
    return previews


def build_structured_changes(
    action: dict,
    state: dict,
    outcome: str,
    social_states: list[dict] | None = None,
    local_plans: list[dict] | None = None,
    decision_context: dict | None = None,
) -> dict:
    """从固定内容计算玩家结果，再串行执行回应者、NPC决策和场景导演。"""
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
            "source_record_id": None,
            "observed_at": state.get("world_time", 0) + action.get("time_cost", 0),
            "precision": "exact",
            "corrects_record_id": None,
        }
        for clue in new_clues
    ]
    for declaration in KNOWLEDGE_DECLARATIONS.get(action["id"], []):
        if outcome in declaration["outcomes"]:
            knowledge.append({
                "source_record_id": None,
                "observed_at": None,
                "precision": "unknown",
                "corrects_record_id": None,
                **{key: value for key, value in declaration.items() if key != "outcomes"},
            })
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
    if decision_context is not None:
        if social_states is None:
            social_states = decision_context.get("social_states", [])
        if local_plans is None:
            local_plans = decision_context.get("local_plans", [])
    social_states = social_states or []
    local_plans = local_plans or []
    before_time = state.get("world_time", 0)
    time_cost = action.get("time_cost", 0)
    after_time = before_time + time_cost
    response = judge_social_response(action, outcome, social_states, local_plans)
    social = build_social_changes(
        action, outcome, after_time, social_states, local_plans, response
    )
    if decision_context is None:
        decision_context = make_decision_context(
            state, social_states, local_plans, [], [], [], 0
        )
    simulation, scenes, autonomy = _build_autonomy_changes(
        deepcopy(decision_context), social_states, local_plans, social, after_time,
        "commission" in state["clues"] or action["id"] == "accept_commission",
    )
    if response is not None:
        autonomy["responses"].append(response)
    knowledge.extend(build_declared_cognition(
        action, outcome, decision_context, after_time
    ))
    game_id = decision_context.get("game_id", "local")
    knowledge = assign_cognition_ids(knowledge, game_id, action["id"])
    simulation["knowledge"] = assign_cognition_ids(
        simulation["knowledge"], game_id, f"{action['id']}:autonomy"
    )
    cognition_records = knowledge + simulation["knowledge"]
    # 校验以行动后时间为准，同时保持原决策上下文不变。
    validation_context = deepcopy(decision_context)
    validation_context["after_time"] = after_time
    validate_cognition_changes(cognition_records, validation_context, {})
    decay = []
    for holder_id in sorted({item["holder_id"] for item in decision_context["knowledge"]}):
        for record in build_cognition_view(
            holder_id, decision_context["knowledge"], after_time
        ):
            if record["kind"] in {"observation", "memory"}:
                decay.append({
                    "holder_id": holder_id,
                    "knowledge_id": record["knowledge_id"],
                    "base_precision": record["precision"],
                    "effective_precision": record["effective_precision"],
                    "elapsed_time": (
                        after_time - record["observed_at"]
                        if record["observed_at"] is not None else None
                    ),
                })
    return {
        "facts_add": facts,
        "clock": clock,
        "knowledge": knowledge,
        "world_time": {
            "before": before_time,
            "after": after_time,
            "time_cost": time_cost,
        },
        "social": social,
        "simulation": simulation,
        "scenes": scenes,
        "autonomy": autonomy,
        "cognition": {
            "world_time": after_time,
            "records": cognition_records,
            "decay": decay,
        },
    }


def _build_autonomy_changes(
    context, social_states, local_plans, social, after_time, has_commission
):
    """每个原到期计划只决策一次；新建立计划不在同一边界链式触发。"""
    simulation = advance_local_simulation(
        after_time, social_states, local_plans, process_plans=False
    )
    autonomy = {"responses": [], "decisions": [], "scenes": []}
    scenes = []
    due_plans = sorted(
        (
            item for item in local_plans
            if item["scope"] == "c01" and item["status"] == "pending"
            and item["due_time"] <= after_time
        ),
        key=lambda item: (item["due_time"], item["plan_id"]),
    )
    if len(due_plans) > 8:
        raise ValueError("单次行动到期计划超过8项上限")
    context["after_time"] = after_time
    context["social_states"] = deepcopy(social_states) + deepcopy(social["states"])
    context["local_plans"] = deepcopy(local_plans)
    context["channels"] = ["remote_message"] if has_commission else []
    for plan in due_plans:
        decision = decide_npc_plan(plan, context)
        directed = select_scene(decision, context)
        autonomy["decisions"].append({
            key: value for key, value in decision.items() if key != "changes"
        })
        autonomy["scenes"].extend(directed["scenes"])
        if directed["scene"] is None:
            continue
        scenes.append(directed["scene"])
        for key in ("plans", "states", "knowledge", "history", "public"):
            simulation[key].extend(directed["changes"][key])
        # 更新只读工作副本，保证多个计划的顺序和重复场景判断确定。
        for update in directed["changes"]["plans"]:
            current = next(
                item for item in context["local_plans"]
                if item["plan_id"] == update["plan_id"]
            )
            current["status"] = update["status"]
        context["knowledge"].extend(deepcopy(directed["changes"]["knowledge"]))
        context["character_history"].extend(deepcopy(directed["changes"]["history"]))
        context.setdefault("activated_scenes", []).append(directed["scene"]["scene_id"])
    return simulation, scenes, autonomy


def apply_plan(plan: dict, state: dict, roll: dict | None) -> dict | None:
    """纯计算主结果；没有案件变化时返回 None，After 不另造行动。"""
    if not plan["case_action"]:
        return None
    action = action_by_id(plan["intent"]["action_id"])
    next_state = resolve_action(state, action, roll["outcome"] if roll else None)
    keys = ("phase", "location", "clock", "world_time", "clues", "ending")
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
    decision_context_hash: str | None = None,
) -> dict:
    """组成版本2完整内部审计；公开接口另行裁剪自主决策细节。"""
    after_revision = state["revision"] + (1 if next_state else 0)
    random_audit = None
    if roll:
        random_audit = {
            "seed": game["seed"],
            "sequence": game["roll_count"],
            **roll,
        }
    stored_changes = deepcopy(structured_changes) if structured_changes else None
    autonomy = (stored_changes or {}).pop("autonomy", None) or {
        "responses": [], "decisions": [], "scenes": [],
    }
    cognition = (stored_changes or {}).pop("cognition", None) or {
        "world_time": state.get("world_time", 0), "records": [], "decay": [],
    }
    autonomy.update({
        "decision_context_hash": decision_context_hash,
        "random_sequence_before": game["roll_count"],
        "random_sequence_after_player": game["roll_count"] + (1 if roll else 0),
    })
    return {
        "audit_version": 3,
        "rules_version": RULES_VERSION,
        "content_version": CONTENT_VERSION,
        "candidates": plan["candidates"],
        "selected_action": plan["selected_action"],
        "pipeline": plan["pipeline"],
        "declaration": plan["declaration"],
        "structured_changes": stored_changes,
        "autonomy": autonomy,
        "cognition": cognition,
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
