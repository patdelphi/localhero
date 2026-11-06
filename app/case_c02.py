"""程序说明：定义 C02《最后一班配送》的固定地点、行动、线索和结局。

本模块只保存案件内容，不读取其他案件状态；跨案关联通过线索元数据表达。
"""

CONTENT_VERSION = "c02-1.0"
CASE_ID = "C02"
CASE_TITLE = "最后一班配送"
CASE_SUBTITLE = "栖光里夜间配送事故与平台推责"
START_LOCATION = "OC-01"
CLOCK_ID = "log_overwrite"
CLOCK_LABEL = "机器人循环日志被覆盖"
CLOCK_MAX = 3
PLAN_SCOPE = "c02"
COMMISSION_CLUE = "c02_commission"
COMMISSION_ACTION = "accept_c02_commission"

# 行动前声明只补充展示元数据，机械后果仍由固定 effects 唯一决定。
ACTION_METADATA = {
    "accept_c02_commission": {
        "target": "零工互助会与受伤配送员陆简",
        "effect": "接受委托并建立公开委托关系",
    },
    "check_storage": {
        "target": "周弥取走的存储片",
        "effect": "确认紧急绕行指令仍然可读",
    },
    "trace_data_cleaner": {
        "target": "数澜路线清洁日志",
        "effect": "发现人工绕行被标为异常，并暴露与 C01 旧凭证的关联",
    },
    "confront_gu": {
        "target": "顾北庭与灰度观察回执",
        "effect": "公开总部批准灰度切换的书面依据",
    },
}

LOCATIONS = {
    "OC-01": {"name": "灰区事务所", "district": "旧城区"},
    "HC-01": {"name": "栖光里商业综合体", "district": "蜂巢区"},
    "HC-04": {"name": "零工互助站", "district": "蜂巢区"},
    "HC-09": {"name": "安澜工程调度点", "district": "蜂巢区"},
}

CLUE_LABELS = {
    "c02_commission": "零工互助会委托：查清栖光里配送事故",
    "collision_scene": "碰撞现场：机器人减速痕迹与行人改道",
    "school_detour": "学校夜间活动临时改道通知",
    "delivery_terminal": "陆简的行车终端显示跟车过近与急停",
    "storage_fragment": "存储片保留周弥发出的紧急绕行指令",
    "narrative_testimony": "夜班商户证实当晚人流路线已改变",
    "cleaning_log": "路线清洁日志把人工安全绕行标为异常停留",
    "legacy_credential_trace": "清洁任务仍由苗雨旧凭证触发，操作者却是邵谦团队",
    "manual_hold_log": "配送机器人曾设置十五分钟手动保持并超时恢复",
    "map_version_gap": "机器人恢复运行时使用未包含改道的地图版本",
    "gray_scale_receipt": "顾北庭保留的“已知限制，灰度观察”回执",
    "platform_risk": "平台把周弥的紧急指令标为异常来源",
}

# 核心线索声明只描述已创作路径；实际权限和结果仍由 ACTIONS 与程序判定决定。
CLUE_DEFINITIONS = {
    "c02_commission": {
        "priority": "necessary",
        "acquisition": [{"action_id": "accept_c02_commission", "outcomes": ["no_roll"]}],
        "alternatives": [],
    },
    "collision_scene": {
        "priority": "necessary",
        "acquisition": [{"action_id": "inspect_scene", "outcomes": ["success", "partial", "escalation"]}],
        "alternatives": [],
    },
    "school_detour": {
        "priority": "advantage",
        "acquisition": [{"action_id": "inspect_scene", "outcomes": ["escalation"]}],
        "alternatives": [{"via": "narrative_testimony", "action_id": "ask_merchant"}],
    },
    "delivery_terminal": {
        "priority": "necessary",
        "acquisition": [{"action_id": "check_terminal", "outcomes": ["success", "partial", "escalation"]}],
        "alternatives": [{"via": "narrative_testimony", "action_id": "ask_merchant"}],
    },
    "storage_fragment": {
        "priority": "necessary",
        "acquisition": [{"action_id": "check_storage", "outcomes": ["success", "partial", "escalation"]}],
        "alternatives": [],
    },
    "narrative_testimony": {
        "priority": "advantage",
        "acquisition": [{"action_id": "ask_merchant", "outcomes": ["success", "partial", "escalation"]}],
        "alternatives": [],
    },
    "cleaning_log": {
        "priority": "necessary",
        "acquisition": [{"action_id": "trace_data_cleaner", "outcomes": ["success", "partial", "escalation"]}],
        "alternatives": [{"via": "delivery_terminal", "action_id": "trace_data_cleaner"}],
    },
    "legacy_credential_trace": {
        "priority": "necessary",
        "acquisition": [{"action_id": "trace_data_cleaner", "outcomes": ["success", "partial", "escalation"]}],
        "alternatives": [],
    },
    "manual_hold_log": {
        "priority": "necessary",
        "acquisition": [{"action_id": "check_manual_hold", "outcomes": ["success", "partial", "escalation"]}],
        "alternatives": [],
    },
    "map_version_gap": {
        "priority": "necessary",
        "acquisition": [{"action_id": "compare_map_version", "outcomes": ["success", "partial", "escalation"]}],
        "alternatives": [{"via": "manual_hold_log", "action_id": "compare_map_version"}],
    },
    "gray_scale_receipt": {
        "priority": "advantage",
        "acquisition": [{"action_id": "confront_gu", "outcomes": ["success", "partial"]}],
        "alternatives": [],
    },
    "platform_risk": {
        "priority": "advantage",
        "acquisition": [{"action_id": "check_terminal", "outcomes": ["escalation"]}],
        "alternatives": [],
    },
}

# 跨案线索只声明关联元数据，不读写 C01 存档。
CROSS_CASE_LINKS = {
    "legacy_credential_trace": {
        "case_id": "C01",
        "case_title": "不存在的人",
        "label": "关联 C01：苗雨旧凭证",
    },
}

# 固定感知与信息传递声明；不存在自动补全人物知识的入口。
KNOWLEDGE_DECLARATIONS = {
    "c02_commission_details": [{
        "holder_id": "zhou_mi", "kind": "testimony", "fact_id": None,
        "content": "周弥说明事故前发出绕行指令，并承认取走存储片。",
        "accuracy": "honest", "visibility": "player", "outcomes": ["no_roll"],
    }],
    "check_terminal": [{
        "holder_id": "lu_jian", "kind": "testimony", "fact_id": "delivery_terminal",
        "content": "陆简确认自己跟车过近，但也指出机器人突然减速。",
        "accuracy": "honest", "visibility": "player",
        "outcomes": ["success", "partial", "escalation"],
    }],
    "confront_gu": [
        {
            "holder_id": "gu_beiting", "kind": "testimony", "fact_id": "gray_scale_receipt",
            "content": "顾北庭承认手动保持到期未续，并交出灰度观察回执。",
            "accuracy": "honest", "visibility": "player", "outcomes": ["success", "partial"],
        },
        {
            "holder_id": "gu_beiting", "kind": "testimony", "fact_id": None,
            "content": "顾北庭只重复总部按已知限制恢复路线，不愿交出回执。",
            "accuracy": "misleading", "visibility": "player", "outcomes": ["escalation"],
        },
    ],
}

# 本阶段不启用到期计划与 NPC 自主候选，保留空定义以复用统一管线。
LOCAL_PLAN_DEFINITIONS = {}
NPC_INITIAL_KNOWLEDGE = {}
AUTONOMY_PLAN_DEFINITIONS = {}
AUTONOMY_EFFECT_DEFINITIONS = {}
SCENE_DEFINITIONS = []


def initial_cognition(game_id, source_event_id):
    """C02 新档不注入额外私密认知，保持空列表。"""
    return []


ENDINGS = {
    "personal_reinstatement": "个人复职",
    "safety_pause": "安全暂停",
    "collective_bargaining": "集体谈判",
}

# 每个行动都声明可出现的地点、阶段、前置线索、掷骰要求和确定性后果。
ACTIONS = [
    {
        "id": "accept_c02_commission",
        "label": "接受零工互助会的委托",
        "aliases": ["接受委托", "接手委托", "接下委托", "接案"],
        "location": "OC-01",
        "phases": ["unoffered", "deferred"],
        "requires_clues": [],
        "requires_roll": False,
        "tendency": "共情",
        "modifier": 0,
        "effects": {"no_roll": {"phase_to": "active", "clues_add": ["c02_commission"]}},
        "narratives": {
            "no_roll": "周弥把事故机器人的存储片放在桌上。零工互助会希望恢复他的账号，也要求平台解释为什么把紧急绕行当成异常指令。你接下委托。",
        },
    },
    {
        "id": "decline_c02_commission",
        "label": "拒绝委托",
        "aliases": ["拒绝周弥", "不接委托", "先不接手"],
        "location": "OC-01",
        "phases": ["unoffered", "deferred"],
        "requires_clues": [],
        "requires_roll": False,
        "tendency": "行动",
        "modifier": 0,
        "effects": {"no_roll": {"phase_to": "deferred", "clock_add": 1}},
        "narratives": {
            "no_roll": "你让周弥先回去。他把存储片重新收进内袋，没有争辩。平台对互助会的关联风控仍在推进，委托留在事务所桌上。",
        },
    },
    {
        "id": "c02_commission_details",
        "label": "询问配送事故细节",
        "aliases": ["问清楚", "了解事故", "问周弥"],
        "location": "OC-01",
        "phases": ["unoffered", "deferred", "active"],
        "requires_clues": [],
        "requires_roll": False,
        "tendency": "共情",
        "modifier": 0,
        "effects": {"no_roll": {}},
        "narratives": {
            "no_roll": "周弥说他看到行人冲进后勤通道，才发出紧急绕行指令；机器人减速后，后面的陆简撞了上来。平台只看指令来源异常，就暂停了他的账号。",
        },
    },
    {
        "id": "travel_hc01",
        "label": "前往栖光里",
        "aliases": ["去栖光里", "前往栖光里综合体", "去事故现场"],
        "location": "OC-01",
        "phases": ["active"],
        "requires_clues": ["c02_commission"],
        "requires_roll": False,
        "tendency": "行动",
        "modifier": 0,
        "effects": {"no_roll": {"location_to": "HC-01"}},
        "narratives": {
            "no_roll": "你换乘进入蜂巢区。栖光里的后勤通道被临时围挡，配送机器人和人工车辆仍从狭窄的侧门进出。",
        },
    },
    {
        "id": "travel_hc04",
        "label": "前往零工互助站",
        "aliases": ["去互助站", "前往互助站", "找零工互助会"],
        "location": "*",
        "phases": ["active"],
        "requires_clues": ["c02_commission"],
        "requires_roll": False,
        "tendency": "行动",
        "modifier": 0,
        "effects": {"no_roll": {"location_to": "HC-04"}},
        "narratives": {
            "no_roll": "互助站里挤着刚被封号的配送员。周弥把存储片锁进后间的旧工具箱，志愿者正逐条整理当晚的接单记录。",
        },
    },
    {
        "id": "travel_hc09",
        "label": "前往安澜工程调度点",
        "aliases": ["去工程调度点", "找顾北庭", "前往调度点"],
        "location": "*",
        "phases": ["active"],
        "requires_clues": ["c02_commission"],
        "requires_roll": False,
        "tendency": "行动",
        "modifier": 0,
        "effects": {"no_roll": {"location_to": "HC-09"}},
        "narratives": {
            "no_roll": "工程调度点的工单墙按安全、居住影响和便利分色，总部面板却只按成本排序。顾北庭正在处理七号楼的水泵告警。",
        },
    },
    {
        "id": "travel_oc01",
        "label": "返回灰区事务所",
        "aliases": ["回事务所", "返回事务所", "回灰区事务所"],
        "location": "*",
        "phases": ["unoffered", "deferred", "active"],
        "requires_clues": [],
        "requires_roll": False,
        "tendency": "行动",
        "modifier": 0,
        "effects": {"no_roll": {"location_to": "OC-01"}},
        "narratives": {
            "no_roll": "你回到事务所。唐葵把新的时间线钉到案件板上，等你决定先走哪条证据路径。",
        },
    },
    {
        "id": "inspect_scene",
        "label": "查看碰撞现场",
        "aliases": ["检查现场", "查看碰撞痕迹", "看事故现场"],
        "location": "HC-01",
        "phases": ["active"],
        "requires_clues": ["c02_commission"],
        "requires_roll": True,
        "tendency": "洞察",
        "modifier": 1,
        "effects": {
            "success": {"clues_add": ["collision_scene"]},
            "partial": {"clues_add": ["collision_scene"], "clock_add": 1},
            "escalation": {"clues_add": ["collision_scene", "school_detour"], "clock_add": 1},
        },
        "narratives": {
            "success": "地面上留着急停后的短痕，机器人转向角与行人改道方向一致，不像蓄意冲撞。",
            "partial": "你确认了碰撞轨迹，但围挡正在撤除，循环日志已经开始覆盖当晚记录。",
            "escalation": "你在围挡下找到学校夜间活动的改道通知；碰撞发生前，人流确实被引到了后勤交界。",
        },
    },
    {
        "id": "ask_merchant",
        "label": "询问夜班商户",
        "aliases": ["问店员", "询问两杯茶", "问夜班商户"],
        "location": "HC-01",
        "phases": ["active"],
        "requires_clues": ["c02_commission"],
        "requires_roll": True,
        "tendency": "共情",
        "modifier": 1,
        "effects": {
            "success": {"clues_add": ["narrative_testimony", "school_detour"]},
            "partial": {"clues_add": ["narrative_testimony"], "clock_add": 1},
            "escalation": {"clues_add": ["narrative_testimony", "school_detour"], "clock_add": 1},
        },
        "narratives": {
            "success": "两杯茶的店员记得当晚学生绕到后勤通道，配送机器人明显减了速，后面的骑手没能及时拉开距离。",
            "partial": "商户愿意证实人流改变，但只肯说这么多；平台的关联风控仍在扩大。",
            "escalation": "店员拿出学校改道通知的照片，也承认周弥平时就常提醒同行注意行人。",
        },
    },
    {
        "id": "check_terminal",
        "label": "调取配送终端记录",
        "aliases": ["查配送终端", "调取行车记录", "看陆简终端"],
        "location": "HC-01",
        "phases": ["active"],
        "requires_clues": ["c02_commission"],
        "requires_roll": True,
        "tendency": "技术",
        "modifier": 1,
        "effects": {
            "success": {"clues_add": ["delivery_terminal"]},
            "partial": {"clues_add": ["delivery_terminal"], "clock_add": 1},
            "escalation": {"clues_add": ["delivery_terminal", "platform_risk"], "clock_add": 1},
        },
        "narratives": {
            "success": "陆简的行车终端显示他跟车过近，同时也记录了机器人无预警减速；紧急指令时间戳早于碰撞。",
            "partial": "你拿到了终端记录，但平台已开始把周弥的指令标记为异常来源。",
            "escalation": "记录证明陆简跟车过近，也显示平台把紧急绕行直接列入封号依据；核心证据仍在。",
        },
    },
    {
        "id": "check_storage",
        "label": "核对周弥的存储片",
        "aliases": ["查存储片", "查看存储片", "核对存储片"],
        "location": "HC-04",
        "phases": ["active"],
        "requires_clues": ["c02_commission"],
        "requires_roll": True,
        "tendency": "洞察",
        "modifier": 0,
        "effects": {
            "success": {"clues_add": ["storage_fragment"]},
            "partial": {"clues_add": ["storage_fragment"], "clock_add": 1},
            "escalation": {"clues_add": ["storage_fragment"], "clock_add": 1},
        },
        "narratives": {
            "success": "存储片里保留着周弥发出的紧急绕行指令，时间早于碰撞，指令目标是避开突然出现的行人。",
            "partial": "你读出紧急指令，但存储片有坏块，只能确认方向，不能恢复完整路线。",
            "escalation": "存储片部分损坏，但紧急指令与行人避让目标仍可辨认；周弥没有伪造事故。",
        },
    },
    {
        "id": "trace_data_cleaner",
        "label": "追查路线清洁日志",
        "aliases": ["查清洁日志", "追查数据清洁", "查路线日志"],
        "location": "HC-04",
        "phases": ["active"],
        "requires_clues": [],
        "requires_clues_any": ["delivery_terminal", "storage_fragment"],
        "requires_roll": True,
        "tendency": "技术",
        "modifier": 0,
        "effects": {
            "success": {"clues_add": ["cleaning_log", "legacy_credential_trace"]},
            "partial": {"clues_add": ["cleaning_log", "legacy_credential_trace"], "clock_add": 1},
            "escalation": {"clues_add": ["cleaning_log", "legacy_credential_trace"], "clock_add": 1},
        },
        "narratives": {
            "success": "清洁日志把多次人工安全绕行标成异常停留，执行任务的仍是苗雨的旧凭证，操作者却属于邵谦团队。",
            "partial": "你确认了错误的清洁规则，也看到旧凭证关联；日志覆盖正在逼近，但核心行仍留有副本。",
            "escalation": "日志残缺，但足以证明安全绕行被降权，且任务来源与 C01 的旧凭证问题相连。",
        },
    },
    {
        "id": "check_manual_hold",
        "label": "核对手动保持日志",
        "aliases": ["查手动保持", "查看保持日志", "核对十五分钟保持"],
        "location": "HC-09",
        "phases": ["active"],
        "requires_clues": ["c02_commission"],
        "requires_roll": True,
        "tendency": "技术",
        "modifier": 1,
        "effects": {
            "success": {"clues_add": ["manual_hold_log"]},
            "partial": {"clues_add": ["manual_hold_log"], "clock_add": 1},
            "escalation": {"clues_add": ["manual_hold_log", "map_version_gap"], "clock_add": 1},
        },
        "narratives": {
            "success": "本地日志显示顾北庭设过十五分钟手动保持，但他去处理水泵告警后没有续期，总部按灰度策略恢复了路线。",
            "partial": "你确认保持设置与超时恢复，但完整历史已同步总部，本地只留短期记录。",
            "escalation": "保持日志还显示恢复时使用的地图版本未包含学校改道，碰撞条件已经具备。",
        },
    },
    {
        "id": "compare_map_version",
        "label": "对照地图版本",
        "aliases": ["查地图版本", "版本对照", "比较地图"],
        "location": "HC-09",
        "phases": ["active"],
        "requires_clues": ["manual_hold_log"],
        "requires_roll": True,
        "tendency": "技术",
        "modifier": 1,
        "effects": {
            "success": {"clues_add": ["map_version_gap"]},
            "partial": {"clues_add": ["map_version_gap"], "clock_add": 1},
            "escalation": {"clues_add": ["map_version_gap"], "clock_add": 1},
        },
        "narratives": {
            "success": "恢复运行时机器人加载的是旧地图，学校改道只存在于另一份版本；两套路线在同一通道里互相冲突。",
            "partial": "版本差异得到确认，但总部开始同步覆盖本地副本，时钟继续推进。",
            "escalation": "你只能保住差异摘要，但足以证明机器人使用了未包含改道的地图版本。",
        },
    },
    {
        "id": "confront_gu",
        "label": "追问顾北庭",
        "aliases": ["找顾北庭", "质问顾北庭", "问灰度报告"],
        "location": "HC-09",
        "phases": ["active"],
        "requires_clues": [],
        "requires_clues_any": ["manual_hold_log", "map_version_gap"],
        "requires_roll": True,
        "tendency": "行动",
        "modifier": 0,
        "effects": {
            "success": {"clues_add": ["gray_scale_receipt"]},
            "partial": {"clues_add": ["gray_scale_receipt"], "clock_add": 1},
            "escalation": {"clues_add": ["platform_risk"], "clock_add": 1},
        },
        "narratives": {
            "success": "顾北庭拿出总部回执：他报告过新调度与手动保持冲突，却被标为“已知限制，灰度观察”。",
            "partial": "他承认自己没续期，也交出回执，但要求不要把他写成唯一责任人。",
            "escalation": "顾北庭拒绝交底，只重复“按已知限制恢复”；平台风控继续收紧，已有证据足以另走路径。",
        },
    },
    {
        "id": "end_personal_reinstatement",
        "label": "选择个人复职",
        "aliases": ["个人复职", "帮周弥恢复账号", "低调复职"],
        "location": "*",
        "phases": ["active"],
        "requires_clues": ["storage_fragment", "delivery_terminal"],
        "requires_clues_any": ["manual_hold_log", "cleaning_log"],
        "requires_roll": False,
        "tendency": "共情",
        "modifier": 0,
        "effects": {"no_roll": {"phase_to": "closed", "ending": "personal_reinstatement"}},
        "narratives": {
            "no_roll": "你提交能证明周弥没有制造事故的最小材料。他的账号恢复并获得补偿，但因取走存储片接受警告；灰度策略只做了局部修补。",
        },
    },
    {
        "id": "end_safety_pause",
        "label": "推动安全暂停",
        "aliases": ["安全暂停", "暂停路线", "要求人流联动"],
        "location": "*",
        "phases": ["active"],
        "requires_clues": ["manual_hold_log", "map_version_gap"],
        "requires_roll": False,
        "tendency": "行动",
        "modifier": 0,
        "effects": {"no_roll": {"phase_to": "closed", "ending": "safety_pause"}},
        "narratives": {
            "no_roll": "你把保持超时与地图版本差异一并递交。安澜暂停新路线，建立人流联动；商户和配送员都要承担效率下降的成本。",
        },
    },
    {
        "id": "end_collective_bargaining",
        "label": "发起集体谈判",
        "aliases": ["集体谈判", "互助会谈判", "集体协商"],
        "location": "*",
        "phases": ["active"],
        "requires_clues": ["cleaning_log", "legacy_credential_trace", "narrative_testimony"],
        "requires_roll": False,
        "tendency": "共情",
        "modifier": 0,
        "effects": {"no_roll": {"phase_to": "closed", "ending": "collective_bargaining"}},
        "narratives": {
            "no_roll": "互助会用事故证据换取正式安全协商渠道。周弥复职，平台承认灰度限制；他过去出售路线数据的旧事也被对方摆上桌面。",
        },
    },
]

# 只有明确声明的移动、调查和社交行动消耗一点游戏内时间。
TIME_COST_ACTIONS = {
    "travel_hc01", "travel_hc04", "travel_hc09", "travel_oc01",
    "inspect_scene", "ask_merchant", "check_terminal", "check_storage",
    "trace_data_cleaner", "check_manual_hold", "compare_map_version",
    "confront_gu",
}
for _action in ACTIONS:
    if _action["id"] in TIME_COST_ACTIONS:
        _action["time_cost"] = 1
