"""程序说明：第九阶段受限情节导演——只允许一种节拍，效果引用固定白名单。"""

from __future__ import annotations

import hashlib
import json
import re

from app.case_registry import CaseBundle, default_case
from app.narrative_context import NPC_NAMES

DIRECTOR_VERSION = "director-1"
DEFAULT_INTERVAL = 5
MIN_INTERVAL = 2
MAX_INTERVAL = 50
MAX_BEATS_PER_GAME = 1
MAX_REASON_CHARS = 80
MAX_EVENT_TEXT_CHARS = 120

# 首批只开放一种节拍，验证通路后再扩展。
BEAT_TYPES = {
    "environment_complication": {
        "label": "环境复杂化",
        "description": "只增加公开环境提示，不改变事实、线索、地点、结局、数值或判定。",
    },
}

# 效果白名单：展示文本固定，机械变化恒为零，模型不能自带文案。
DIRECTOR_EFFECTS = {
    "env.rain_gutter": {
        "beat_type": "environment_complication",
        "text": "雨势忽然加重，门外的排水沟开始持续作响。",
        "clock_delta": 0,
        "fact_changes": 0,
    },
    "env.light_flicker": {
        "beat_type": "environment_complication",
        "text": "顶灯短暂闪了一下，阴影在墙面挪动。",
        "clock_delta": 0,
        "fact_changes": 0,
    },
    "env.door_rattle": {
        "beat_type": "environment_complication",
        "text": "风压让门框发出轻响，走廊外的声音短暂清晰起来。",
        "clock_delta": 0,
        "fact_changes": 0,
    },
}

# 理由只用于审计，不得包含数字、人物、地点、线索或内部术语。
SENSITIVE_WORDS = ("线索", "结局", "时钟", "判定", "评分", "骰", "隐藏", "真相")
DIGIT_PATTERN = re.compile(r"[0-9０-９]")


def _forbidden_tokens(case: CaseBundle | None = None) -> set[str]:
    """汇总固定内容中的人物、地点与线索名称。"""
    bundle = case or default_case()
    tokens = set(NPC_NAMES.values())
    tokens.update(
        item.get("name") for item in bundle.locations.values() if item.get("name")
    )
    tokens.update(bundle.clue_labels.values())
    return {token for token in tokens if token}


FORBIDDEN_TOKENS = _forbidden_tokens()


def count_actions_since_last_beat(events: list[dict]) -> int:
    """统计最后一次已接受节拍之后提交的行动数。"""
    count = 0
    for event in reversed(events or []):
        if event.get("kind") == "director_beat":
            break
        if event.get("kind") == "action_committed":
            count += 1
    return count


def accepted_beats(events: list[dict]) -> list[str]:
    """按提交顺序返回已接受节拍类型，用于拒绝重复。"""
    return [
        (event.get("payload") or {}).get("beat_type")
        for event in events or []
        if event.get("kind") == "director_beat"
    ]


def proposal_context(intent: dict, location_id: str, action_seq: int) -> dict:
    """构造只含公开信息的提案上下文，不暴露隐藏真相。"""
    return {
        "节拍类型": "environment_complication",
        "当前行动编号": intent.get("action_id") or intent.get("kind"),
        "当前行动": intent.get("label") or intent.get("kind"),
        "当前地点": location_id,
        "动作序号": action_seq,
        "可选效果": [
            {"effect_id": effect_id, "text": item["text"]}
            for effect_id, item in DIRECTOR_EFFECTS.items()
            if item["beat_type"] == "environment_complication"
        ],
        "限制": "只能选择可选效果；不得新增人物、地点、线索、结局、数值或判定。",
    }


def evaluate_director(
    events: list[dict],
    model,
    intent: dict,
    location_id: str,
    interval: int = DEFAULT_INTERVAL,
    enabled: bool = True,
    case: CaseBundle | None = None,
) -> dict | None:
    """生成审计 v4 的情节导演段；关闭时返回 None，保持第八阶段结构。"""
    if not enabled:
        return None

    interval = max(MIN_INTERVAL, min(MAX_INTERVAL, int(interval)))
    since_last = count_actions_since_last_beat(events)
    previous = accepted_beats(events)
    action_seq = sum(1 for event in events or [] if event.get("kind") == "action_committed")
    section = {
        "version": DIRECTOR_VERSION,
        "enabled": True,
        "trigger": {
            "checked": False,
            "rule_id": "director.trigger_cooldown",
            "actions_since_last": since_last,
            "interval": interval,
            "max_beats_per_game": MAX_BEATS_PER_GAME,
        },
        "proposal": None,
        "validation": None,
        "accepted": False,
        "effect": None,
    }

    # 同档已接受过该节拍时直接拒绝，避免重复和无限生成。
    if previous.count("environment_complication") >= MAX_BEATS_PER_GAME:
        section["trigger"].update({
            "checked": True,
            "rule_id": "director.trigger_beat_exhausted",
        })
        section["validation"] = {
            "accepted": False,
            "rule_id": "director.no_repeat_beat",
            "reason": "同档已接受过环境复杂化节拍",
        }
        return section

    if since_last < interval:
        return section

    section["trigger"].update({"checked": True, "rule_id": "director.trigger_ready"})
    raw = _ask_model(model, proposal_context(intent, location_id, action_seq + 1))
    if raw is None:
        section["validation"] = {
            "accepted": False,
            "rule_id": "director.proposal_unavailable",
            "reason": "模型未返回可用提案",
        }
        return section

    proposal = _normalize_proposal(raw)
    validation = validate_proposal(proposal, intent, previous, case)
    section["proposal"] = proposal
    section["validation"] = validation
    if validation["accepted"]:
        effect = DIRECTOR_EFFECTS[proposal["effect_id"]]
        section["effect"] = {
            "beat_type": effect["beat_type"],
            "effect_id": proposal["effect_id"],
            "text": effect["text"],
            "clock_delta": effect["clock_delta"],
            "fact_changes": effect["fact_changes"],
        }
        section["accepted"] = True
    return section


def validate_proposal(
    proposal: dict,
    intent: dict,
    previous: list[str],
    case: CaseBundle | None = None,
) -> dict:
    """按固定规则校验提案；拒绝时给出稳定规则编号与审计理由。"""
    forbidden = _forbidden_tokens(case)
    expected_target = intent.get("action_id") or intent.get("kind")
    if not isinstance(proposal.get("beat_type"), str) or not isinstance(
        proposal.get("effect_id"), str
    ):
        return _reject("director.proposal_invalid", "提案缺少必要字段")
    if proposal["beat_type"] not in BEAT_TYPES:
        return _reject("director.beat_type_not_allowed", "节拍类型不在白名单")
    effect = DIRECTOR_EFFECTS.get(proposal["effect_id"])
    if effect is None:
        return _reject("director.effect_not_allowed", "效果编号不在白名单")
    if effect["beat_type"] != proposal["beat_type"]:
        return _reject("director.effect_beat_mismatch", "效果不属于该节拍")
    if proposal.get("target_action") != expected_target:
        return _reject("director.target_mismatch", "目标行动与当前行动不一致")
    reason = proposal.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return _reject("director.reason_rejected", "提案理由缺失")
    if len(reason) > MAX_REASON_CHARS or DIGIT_PATTERN.search(reason):
        return _reject("director.reason_rejected", "提案理由超长或含数字")
    if any(token in reason for token in forbidden) or any(
        word in reason for word in SENSITIVE_WORDS
    ):
        return _reject("director.reason_rejected", "提案理由含私密或内部信息")
    if effect.get("clock_delta") != 0 or effect.get("fact_changes") != 0:
        return _reject("director.mechanical_change_rejected", "效果不得改变机械状态")
    if previous.count("environment_complication") >= MAX_BEATS_PER_GAME:
        return _reject("director.no_repeat_beat", "同档已接受过环境复杂化节拍")
    return {
        "accepted": True,
        "rule_id": "director.accepted",
        "reason": "提案通过白名单与冷却校验",
    }


def validate_director_record(director: dict, intent: dict) -> dict:
    """校验已保存的审计段；回放不重新询问模型，只核对结构与效果。"""
    if not isinstance(director, dict) or director.get("version") != DIRECTOR_VERSION:
        return _reject("director.proposal_invalid", "审计段版本或结构不合法")
    if not director.get("accepted"):
        return {
            "accepted": False,
            "rule_id": (director.get("validation") or {}).get("rule_id")
            or "director.rejected",
            "reason": (director.get("validation") or {}).get("reason") or "提案被拒绝",
        }
    proposal = director.get("proposal")
    effect = director.get("effect")
    if not isinstance(proposal, dict) or not isinstance(effect, dict):
        return _reject("director.proposal_invalid", "已接受提案缺少必要字段")
    if effect.get("effect_id") != proposal.get("effect_id"):
        return _reject("director.effect_not_allowed", "效果编号与提案不一致")
    definition = DIRECTOR_EFFECTS.get(effect.get("effect_id"))
    if definition is None:
        return _reject("director.effect_not_allowed", "效果编号不在白名单")
    if effect.get("text") != definition["text"]:
        return _reject("director.effect_not_allowed", "展示文本与白名单不一致")
    if effect.get("clock_delta") != 0 or effect.get("fact_changes") != 0:
        return _reject("director.mechanical_change_rejected", "效果不得改变机械状态")
    expected_target = intent.get("action_id") or intent.get("kind")
    if proposal.get("target_action") != expected_target:
        return _reject("director.target_mismatch", "目标行动与已保存意图不一致")
    return {"accepted": True, "rule_id": "director.accepted", "reason": "已保存提案一致"}


def director_event_payload(director: dict) -> dict:
    """生成可回放的公开事件负载；只含审计可见字段。"""
    proposal = director.get("proposal") or {}
    effect = director.get("effect") or {}
    payload = {
        "beat_type": proposal.get("beat_type"),
        "effect_id": proposal.get("effect_id"),
        "text": effect.get("text"),
        "target_action": proposal.get("target_action"),
        "proposal_id": proposal.get("proposal_id"),
        "source": proposal.get("source"),
        "reason": proposal.get("reason"),
    }
    return validate_director_event_payload(payload)


def validate_director_event_payload(payload: dict) -> dict:
    """校验事件负载，拒绝任何额外字段或非白名单文本。"""
    allowed = {
        "beat_type", "effect_id", "text", "target_action",
        "proposal_id", "source", "reason",
    }
    if not isinstance(payload, dict) or set(payload) != allowed:
        raise ValueError("情节节拍事件字段不完整或包含未声明字段")
    definition = DIRECTOR_EFFECTS.get(payload["effect_id"])
    if (
        payload["beat_type"] not in BEAT_TYPES
        or definition is None
        or definition["beat_type"] != payload["beat_type"]
        or payload["text"] != definition["text"]
        or len(payload["text"]) > MAX_EVENT_TEXT_CHARS
    ):
        raise ValueError("情节节拍事件与白名单不一致")
    return payload


def _ask_model(model, context: dict) -> dict | None:
    """调用模型的提案能力；任何失败都转为无提案，不阻断行动。"""
    propose = getattr(model, "propose_director", None)
    if not callable(propose):
        return None
    try:
        proposal = propose(context)
    except Exception:
        return None
    return proposal if isinstance(proposal, dict) else None


def _normalize_proposal(raw: dict) -> dict:
    """补齐提案标识与来源，不改变模型给出的白名单编号。"""
    proposal = {
        "beat_type": raw.get("beat_type"),
        "effect_id": raw.get("effect_id"),
        "target_action": raw.get("target_action"),
        "reason": raw.get("reason"),
        "source": raw.get("source") or "model",
    }
    canonical = json.dumps(proposal, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    proposal["proposal_id"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return proposal


def _reject(rule_id: str, reason: str) -> dict:
    """构造统一的拒绝结果。"""
    return {"accepted": False, "rule_id": rule_id, "reason": reason}
