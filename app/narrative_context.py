"""程序说明：只从已提交事实构建叙事上下文，并提供固定口吻、裁剪与重复检测。"""

from __future__ import annotations

import json

from app.case_registry import CaseBundle, default_case

# 上下文与重复检测参数集中定义，便于测试和后续调整。
MAX_CONTEXT_CHARS = 1200
RECENT_ACTION_LIMIT = 3
KNOWN_CLUE_LIMIT = 8
LAST_NARRATIVE_CHARS = 120
REPEAT_NGRAM = 6
REPEAT_SIMILARITY_THRESHOLD = 0.35

OUTCOME_LABELS = {
    "no_roll": "无需判定",
    "success": "成功",
    "partial": "有代价成功",
    "escalation": "局势升级",
}

INTENT_LABELS = {
    "talk_tang": "与唐葵交谈",
    "inspect_device": "检查设备",
    "inspect": "查看现场",
    "improvise": "临时行动",
}

# 地点提示来自固定案件内容，只用于保持场景连贯，不含隐藏真相。
LOCATION_HINTS = {
    "OC-01": "狭小的事务所，案件板靠墙，窗外是旧城区的雨。",
    "HC-07": "蜂巢区的高密度公寓，走廊里装着项目终端。",
    "OC-03": "夜诊灯常亮的社区诊所，病历按匿名编号排列。",
    "LG-05": "老港区的货运场，雨棚下堆着短驳箱与纸质签单。",
    "HC-01": "蜂巢区的高密度商业综合体，后勤通道被围挡切开。",
    "HC-04": "零工互助站的窄房间，墙上贴满被封号者的接单记录。",
    "HC-09": "安澜工程调度点，工单墙按安全与便利分色。",
}

# 在场人物只按地点固定映射，不推断临时到访或隐藏行程。
PRESENT_NPCS_BY_LOCATION = {
    "OC-01": ["tang_kui"],
    "HC-07": ["fang_sheng"],
    "OC-03": ["lin_yanzhou"],
    "LG-05": [],
    "HC-01": ["zhou_mi", "lu_jian"],
    "HC-04": ["zhou_mi"],
    "HC-09": ["gu_beiting"],
}

NPC_NAMES = {
    "fang_sheng": "方笙",
    "tang_kui": "唐葵",
    "lin_yanzhou": "林砚舟",
    "miao_yu": "苗雨",
    "a_luo": "阿洛",
    "shao_qian": "邵谦",
    "zhou_mi": "周弥",
    "lu_jian": "陆简",
    "gu_beiting": "顾北庭",
}

# 口吻档案只约束表达方式，不授权新增台词、决定或人物关系。
NARRATIVE_VOICE_PROFILES = {
    "fang_sheng": {
        "人物": "方笙",
        "称呼": "你",
        "句长": "短句，句子之间留停顿",
        "用词": "谨慎、具体，多说担心和请求",
        "禁忌": "不替自己辩解，不提系统内部流程，不承诺未提交的结果",
    },
    "tang_kui": {
        "人物": "唐葵",
        "称呼": "你",
        "句长": "短句，节奏干脆",
        "用词": "事务所行话，少形容词",
        "禁忌": "不提案件评分，不替玩家作决定",
    },
    "lin_yanzhou": {
        "人物": "林砚舟",
        "称呼": "你",
        "句长": "中短句，措辞完整",
        "用词": "医疗与记录术语，语气审慎",
        "禁忌": "不替患者下结论，不透露未公开病历",
    },
    "miao_yu": {
        "人物": "苗雨",
        "称呼": "你",
        "句长": "很短，常省略主语",
        "用词": "疲惫、回避承诺",
        "禁忌": "不说明藏身细节，不主动要求被找回",
    },
    "a_luo": {
        "人物": "阿洛",
        "称呼": "你",
        "句长": "短句，口语化",
        "用词": "直接、带药摊行话",
        "禁忌": "不夸张，不替苗雨表态",
    },
    "zhou_mi": {
        "人物": "周弥",
        "称呼": "你",
        "句长": "短句，常先复述问题再回答",
        "用词": "配送与平台术语，语气疲惫",
        "禁忌": "不宣称自己完全无辜，不提未提交的路线数据",
    },
    "lu_jian": {
        "人物": "陆简",
        "称呼": "你",
        "句长": "短句，语速快",
        "用词": "骑手行话，强调时间与距离",
        "禁忌": "不替平台解释算法，不隐瞒跟车距离",
    },
    "gu_beiting": {
        "人物": "顾北庭",
        "称呼": "你",
        "句长": "中短句，先给结论",
        "用词": "工单、安全与成本术语",
        "禁忌": "不否认手动保持超时，不透露总部未提交计划",
    },
}

# 裁剪顺序从低优先级到高优先级；当前地点最后处理。
TRIM_ORDER = ("口吻参考", "上一条叙事结尾", "玩家已知线索", "最近行动", "在场人物", "地点提示", "当前地点")


def build_narrative_context(
    events,
    case_state,
    knowledge,
    action,
    case: CaseBundle | None = None,
) -> dict:
    """派生最近行动、地点、在场人物、上一条叙事结尾与玩家已知线索。"""
    bundle = case or default_case()
    case_state = case_state or {}
    location_id = case_state.get("location")
    location = bundle.locations.get(location_id, {})
    location_name = location.get("name") or location_id or "未知地点"
    district = location.get("district")
    current_location = f"{location_name}（{district}）" if district else location_name

    present_ids = PRESENT_NPCS_BY_LOCATION.get(location_id, [])
    present = [NPC_NAMES[npc_id] for npc_id in present_ids if npc_id in NPC_NAMES]
    voices = [
        dict(NARRATIVE_VOICE_PROFILES[npc_id])
        for npc_id in present_ids
        if npc_id in NARRATIVE_VOICE_PROFILES
    ]

    action_id = (action or {}).get("id")
    recent_actions = []
    for event in events or []:
        if event.get("kind") != "action_committed":
            continue
        # 当前行动已经提交，但它的叙事尚未生成，不得当作前情。
        if action_id and event.get("action_id") == action_id:
            continue
        payload = event.get("payload") or {}
        intent = payload.get("intent") or {}
        outcome = (payload.get("roll") or {}).get("outcome", "no_roll")
        recent_actions.append({
            "行动": intent.get("label") or INTENT_LABELS.get(intent.get("kind"), "尝试行动"),
            "判定": OUTCOME_LABELS.get(outcome, outcome),
        })
    recent_actions = recent_actions[-RECENT_ACTION_LIMIT:]

    last_narrative = ""
    for event in reversed(events or []):
        if event.get("kind") != "narrative_completed":
            continue
        if action_id and event.get("action_id") == action_id:
            continue
        text = (event.get("payload") or {}).get("text") or ""
        last_narrative = text[-LAST_NARRATIVE_CHARS:]
        break

    known_clues = []
    for item in knowledge or []:
        # 即使调用方传入完整认知表，也只接受明确对玩家公开的记录。
        if item.get("visibility") != "player":
            continue
        content = item.get("content")
        if content and content not in known_clues:
            known_clues.append(content)
    known_clues = known_clues[-KNOWN_CLUE_LIMIT:]

    return {
        "当前地点": current_location,
        "地点提示": LOCATION_HINTS.get(location_id, ""),
        "在场人物": present,
        "口吻参考": voices,
        "最近行动": recent_actions,
        "上一条叙事结尾": last_narrative,
        "玩家已知线索": known_clues,
    }


def previous_narrative_texts(events, limit: int = 2) -> list[str]:
    """按提交顺序返回最近几条已完成叙事，供重复检测使用。"""
    texts = []
    for event in events or []:
        if event.get("kind") != "narrative_completed":
            continue
        text = (event.get("payload") or {}).get("text") or ""
        if text:
            texts.append(text)
    return texts[-limit:] if limit else []


def trim_context(context: dict, max_chars: int = MAX_CONTEXT_CHARS) -> dict:
    """按优先级裁剪上下文，确保序列化长度不超过上限。"""
    trimmed_context = dict(context)
    if context_size(trimmed_context) <= max_chars:
        return {
            "context": trimmed_context,
            "size": context_size(trimmed_context),
            "trimmed": False,
            "dropped": [],
        }

    dropped = []
    for key in TRIM_ORDER:
        if context_size(trimmed_context) <= max_chars:
            break
        if key not in trimmed_context:
            continue
        value = trimmed_context[key]
        if isinstance(value, list):
            # 列表从末尾逐项移除，保留更靠前（通常更近）的条目。
            while value and context_size(trimmed_context) > max_chars:
                value = value[:-1]
                trimmed_context[key] = value
            if not value:
                trimmed_context.pop(key, None)
                dropped.append(key)
        else:
            trimmed_context.pop(key, None)
            dropped.append(key)

    # 极端情况下仍超长时，最后才缩短当前地点，保证请求体有界。
    if context_size(trimmed_context) > max_chars and trimmed_context.get("当前地点"):
        trimmed_context["当前地点"] = trimmed_context["当前地点"][: max(1, max_chars // 4)]
        if "当前地点" not in dropped:
            dropped.append("当前地点")

    return {
        "context": trimmed_context,
        "size": context_size(trimmed_context),
        "trimmed": True,
        "dropped": dropped,
    }


def context_size(context: dict) -> int:
    """返回中文上下文 JSON 的字符长度，用于统一裁剪判断。"""
    return len(json.dumps(context, ensure_ascii=False))


def ngram_similarity(left: str, right: str, n: int = REPEAT_NGRAM) -> float:
    """用字符 n-gram 的 Jaccard 相似度检测连续叙事雷同。"""
    left_text = _normalize(left)
    right_text = _normalize(right)
    if left_text == right_text:
        return 1.0
    if len(left_text) < n or len(right_text) < n:
        return 0.0
    left_grams = {left_text[index : index + n] for index in range(len(left_text) - n + 1)}
    right_grams = {right_text[index : index + n] for index in range(len(right_text) - n + 1)}
    union = left_grams | right_grams
    if not union:
        return 0.0
    return len(left_grams & right_grams) / len(union)


def _normalize(text: str) -> str:
    """去掉空白与常见标点，避免格式差异掩盖重复。"""
    ignored = set(" \t\r\n，。！？；：、“”‘’（）《》…—－-.,!?;:")
    return "".join(char for char in (text or "") if char not in ignored)
