"""程序说明：定义 C01《不存在的人》小型单案的固定地点、行动、线索和结局。"""

CONTENT_VERSION = "c01-1.3"

# 行动前声明只补充展示元数据，机械后果仍由下方固定 effects 唯一决定。
ACTION_METADATA = {
    "accept_commission": {
        "target": "方笙与失踪的苗雨",
        "effect": "接受委托并建立公开委托关系",
    },
    "reassure_fangsheng": {
        "target": "方笙与苗雨的安全承诺",
        "effect": "方笙态度缓和，并建立公开补充计划",
    },
    "check_shared_account": {
        "target": "新栖公寓项目共享排班",
        "effect": "确认共享账户，坏骰仍保留核心证据并可能暴露风险警告",
    },
    "contact_miaoyu": {"target": "白鹭滞留区的苗雨与阿洛药摊"},
    "confront_shaoqian": {"target": "邵谦及旧凭证使用责任"},
}

# 案件地点只开放四个，足够覆盖“生活路径”和“劳动路径”两条核心调查线。
LOCATIONS = {
    "OC-01": {"name": "灰区事务所", "district": "旧城区"},
    "HC-07": {"name": "新栖公寓", "district": "蜂巢区"},
    "OC-03": {"name": "青苔诊所", "district": "旧城区"},
    "LG-05": {"name": "白绳货运场", "district": "老港区"},
}

# 线索由程序固定发放，模拟模型不得自行创造线索。
CLUE_LABELS = {
    "commission": "方笙委托：寻找失踪的苗雨",
    "fangsheng_present": "方笙住处仍保留苗雨的生活痕迹",
    "project_export": "项目导出显示超额生产账户",
    "export_delayed": "导出被推迟，但账户关系异常已暴露",
    "shared_account": "共享排班证明少数凭证管理多人工作",
    "risk_warning": "项目曾收到共享账户风险警告",
    "shaqian_admission": "邵谦承认继续使用旧凭证",
    "anonymous_patient": "青苔诊所有匿名女性就诊记录",
    "clinic_hint": "诊所提到患者乘白绳短驳离开",
    "freight_manifest": "货运签显示苗雨前往沉没带",
    "manifest_alternative": "货运记录残缺，但能确认离开方向",
    "miaoyu_alive": "苗雨仍在世，暂住白鹭滞留区",
}

# 核心线索声明只描述已创作路径；实际权限和结果仍由 ACTIONS 与程序判定决定。
CLUE_DEFINITIONS = {
    "commission": {
        "priority": "necessary",
        "acquisition": [{"action_id": "accept_commission", "outcomes": ["no_roll"]}],
        "alternatives": [],
    },
    "fangsheng_present": {
        "priority": "advantage",
        "acquisition": [{"action_id": "inspect_fangsheng_room", "outcomes": ["success", "partial", "escalation"]}],
        "alternatives": [],
    },
    "project_export": {
        "priority": "necessary",
        "acquisition": [{"action_id": "request_project_export", "outcomes": ["success", "partial"]}],
        "alternatives": [{"via": "retry_export", "action_id": "request_project_export"}],
    },
    "export_delayed": {
        "priority": "advantage",
        "acquisition": [{"action_id": "request_project_export", "outcomes": ["escalation"]}],
        "alternatives": [{"via": "retry_export", "action_id": "request_project_export"}],
    },
    "shared_account": {
        "priority": "necessary",
        "acquisition": [{"action_id": "check_shared_account", "outcomes": ["success", "partial", "escalation"]}],
        "alternatives": [
            {"via": "project_export", "action_id": "check_shared_account"},
            {"via": "export_delayed", "action_id": "check_shared_account"},
        ],
    },
    "risk_warning": {
        "priority": "advantage",
        "acquisition": [{"action_id": "check_shared_account", "outcomes": ["escalation"]}],
        "alternatives": [],
    },
    "shaqian_admission": {
        "priority": "advantage",
        "acquisition": [{"action_id": "confront_shaoqian", "outcomes": ["success", "partial"]}],
        "alternatives": [{"via": "shared_account", "action_id": "end_collective_review"}],
    },
    "anonymous_patient": {
        "priority": "necessary",
        "acquisition": [{"action_id": "ask_anonymous_patient", "outcomes": ["success", "partial", "escalation"]}],
        "alternatives": [],
    },
    "clinic_hint": {
        "priority": "advantage",
        "acquisition": [{"action_id": "ask_anonymous_patient", "outcomes": ["escalation"]}],
        "alternatives": [],
    },
    "freight_manifest": {
        "priority": "necessary",
        "acquisition": [{"action_id": "check_freight_record", "outcomes": ["success", "partial"]}],
        "alternatives": [{"via": "manifest_alternative", "action_id": "contact_miaoyu"}],
    },
    "manifest_alternative": {
        "priority": "necessary",
        "acquisition": [{"action_id": "check_freight_record", "outcomes": ["escalation"]}],
        "alternatives": [{"via": "retry_freight_record", "action_id": "check_freight_record"}],
    },
    "miaoyu_alive": {
        "priority": "necessary",
        "acquisition": [{"action_id": "contact_miaoyu", "outcomes": ["success", "partial", "escalation"]}],
        "alternatives": [
            {"via": "freight_manifest", "action_id": "contact_miaoyu"},
            {"via": "manifest_alternative", "action_id": "contact_miaoyu"},
        ],
    },
}

# 固定感知与信息传递声明；不存在根据主持人秘密自动补全人物知识的入口。
KNOWLEDGE_DECLARATIONS = {
    "commission_details": [{
        "holder_id": "fang_sheng", "kind": "testimony", "fact_id": None,
        "content": "方笙说明苗雨身份验证异常及最后收到的自动短讯。",
        "accuracy": "honest", "visibility": "player", "outcomes": ["no_roll"],
    }],
    "confront_shaoqian": [
        {
            "holder_id": "shao_qian", "kind": "testimony", "fact_id": "shaqian_admission",
            "content": "邵谦承认旧凭证仍在使用。",
            "accuracy": "honest", "visibility": "player", "outcomes": ["success", "partial"],
        },
        {
            "holder_id": "shao_qian", "kind": "testimony", "fact_id": None,
            "content": "邵谦拒绝承认旧凭证仍在使用，只让调查者去找公司。",
            "accuracy": "misleading", "visibility": "player", "outcomes": ["escalation"],
        },
    ],
    "ask_anonymous_patient": [{
        "holder_id": "lin_yanzhou", "kind": "testimony", "fact_id": "anonymous_patient",
        "content": "林砚舟确认匿名女性的就诊体征与苗雨相符。",
        "accuracy": "honest", "visibility": "player",
        "outcomes": ["success", "partial", "escalation"],
    }],
    "contact_miaoyu": [{
        "holder_id": "a_luo", "kind": "testimony", "fact_id": "miaoyu_alive",
        "content": "阿洛确认苗雨安全，暂住白鹭滞留区。",
        "accuracy": "honest", "visibility": "player",
        "outcomes": ["success", "partial", "escalation"],
    }],
}

# 固定局部计划只声明到期产物，不允许模型提供任意效果。
LOCAL_PLAN_DEFINITIONS = {
    "fangsheng_followup": {
        "testimony": {
            "holder_id": "fang_sheng",
            "kind": "testimony",
            "fact_id": None,
            "content": "方笙补充了旧排班中的共享账户备注。",
            "accuracy": "honest",
            "visibility": "player",
        },
        "history": "方笙补充了旧排班中的共享账户备注。",
    },
}

# NPC 初始知识只代表人物自己知道的内容，不包含主持人或其他人物秘密。
NPC_INITIAL_KNOWLEDGE = {
    "fang_sheng": ["fang_sheng:old_shift_schedule"],
}


def initial_cognition(game_id, source_event_id):
    """生成新档方笙的固定观察、来源记忆和个人过度推断。"""
    definitions = [
        ("old_shift_observation", "observation", None, "方笙观察过旧排班。", "direct"),
        ("old_shift_schedule", "memory", "old_shift_observation", "方笙记得旧排班及共享账户备注。", "honest"),
        ("last_login_observation", "observation", None, "方笙观察到邵谦凭证的最后登录记录。", "direct"),
        ("last_login_memory", "memory", "last_login_observation", "方笙记得邵谦凭证的最后登录记录。", "honest"),
        ("last_login_inference", "memory", "last_login_memory", "方笙推断：当晚只有邵谦使用凭证。", "honest"),
    ]
    records = []
    for key, kind, source_key, content, accuracy in definitions:
        source_id = f"{game_id}:fang_sheng:{source_key}" if source_key else None
        records.append({
            "id": f"{game_id}:fang_sheng:{key}",
            "knowledge_id": f"{game_id}:fang_sheng:{key}",
            "game_id": game_id,
            "holder_id": "fang_sheng",
            "kind": kind,
            "source_event_id": source_event_id,
            "fact_id": None,
            "content": content,
            "accuracy": accuracy,
            "visibility": "private",
            "source_record_id": source_id,
            "observed_at": 0,
            "precision": "exact",
            "corrects_record_id": None,
        })
    return records

# 固定候选只引用下方效果编号，模型和调用方不能提交任意效果 JSON。
AUTONOMY_PLAN_DEFINITIONS = {
    "fangsheng_followup": {
        "candidates": [
            {
                "candidate_id": "share_schedule",
                "effect_id": "share_schedule_testimony",
                "requires_knowledge": ["fang_sheng:old_shift_schedule"],
                "min_precision": {"fang_sheng:old_shift_schedule": "exact"},
                "min_trust": 1,
                "requires_memory": "优先确认苗雨安全",
                "score": {"goal": 3, "knowledge": 2, "risk": 0},
                "selection_reason_codes": [
                    "protect_miaoyu", "safety_promise", "sufficient_trust",
                ],
            },
            {
                "candidate_id": "share_safe_reminder",
                "effect_id": "share_safe_reminder_testimony",
                "requires_knowledge": ["fang_sheng:old_shift_schedule"],
                "min_precision": {"fang_sheng:old_shift_schedule": "vague"},
                "score": {"goal": 1, "knowledge": 2, "risk": -1},
                "selection_reason_codes": ["protect_miaoyu", "cautious_reminder"],
            },
            {
                "candidate_id": "wait",
                "effect_id": "wait_without_testimony",
                "requires_knowledge": [],
                "score": {"goal": 0, "knowledge": 0, "risk": 0},
                "selection_reason_codes": ["wait_for_next_boundary"],
            },
        ],
    },
}

AUTONOMY_EFFECT_DEFINITIONS = {
    "share_schedule_testimony": {
        "complete_plan": True,
        "knowledge_source": "fang_sheng:old_shift_schedule",
        "correction_id": "fang_sheng:last_login_retraction",
        "testimony": LOCAL_PLAN_DEFINITIONS["fangsheng_followup"]["testimony"],
        "history": LOCAL_PLAN_DEFINITIONS["fangsheng_followup"]["history"],
        "public": LOCAL_PLAN_DEFINITIONS["fangsheng_followup"]["history"],
    },
    "share_safe_reminder_testimony": {
        "complete_plan": True,
        "knowledge_source": "fang_sheng:old_shift_schedule",
        "testimony": {
            "holder_id": "fang_sheng", "kind": "testimony", "fact_id": None,
            "content": "方笙谨慎提醒：旧排班里有需要核对的共享账户。",
            "accuracy": "honest", "visibility": "player",
        },
        "history": "方笙给出了一条谨慎的旧排班提醒。",
        "public": "方笙给出了一条谨慎的旧排班提醒。",
    },
    "wait_without_testimony": {"complete_plan": False},
}

# 场景只负责固定呈现，不声明任何候选之外的机械效果。
SCENE_DEFINITIONS = [
    {
        "scene_id": "fangsheng_remote_schedule",
        "candidate_id": "share_schedule",
        "plan_id": "fangsheng_followup",
        "priority": 10,
        "requires_relationship": "委托人",
        "requires_knowledge": ["fang_sheng:old_shift_schedule"],
        "min_precision": {"fang_sheng:old_shift_schedule": "exact"},
        "channel": "remote_message",
        "presentation_key": "fangsheng_remote_schedule",
        "repeatable": False,
    },
    {
        "scene_id": "fangsheng_remote_reminder",
        "candidate_id": "share_safe_reminder",
        "plan_id": "fangsheng_followup",
        "priority": 10,
        "requires_relationship": "委托人",
        "requires_knowledge": ["fang_sheng:old_shift_schedule"],
        "min_precision": {"fang_sheng:old_shift_schedule": "vague"},
        "channel": "remote_message",
        "presentation_key": "fangsheng_remote_reminder",
        "repeatable": False,
    },
]

ENDINGS = {
    "personal_review": "低调个人复核",
    "collective_review": "提交集体证据",
    "stop_tracing": "尊重苗雨意愿，停止追查",
}

# 每个行动都声明可出现的地点、阶段、前置线索、掷骰要求和确定性后果。
ACTIONS = [
    {
        "id": "accept_commission",
        "label": "接受方笙的委托",
        "aliases": ["接受委托", "接手委托", "接下委托", "接案"],
        "location": "OC-01",
        "phases": ["unoffered", "deferred"],
        "requires_clues": [],
        "requires_roll": False,
        "tendency": "共情",
        "modifier": 0,
        "effects": {"no_roll": {"phase_to": "active", "clues_add": ["commission"]}},
        "narratives": {
            "no_roll": "方笙把皱巴巴的项目表推到你面前。她怕代领任务和借用凭证曝光，却更怕苗雨真的被系统抹掉。你接下委托，唐葵开始整理案件板。",
        },
    },
    {
        "id": "decline_commission",
        "label": "拒绝委托",
        "aliases": ["拒绝方笙", "不接委托", "先不接手"],
        "location": "OC-01",
        "phases": ["unoffered", "deferred"],
        "requires_clues": [],
        "requires_roll": False,
        "tendency": "行动",
        "modifier": 0,
        "effects": {"no_roll": {"phase_to": "deferred", "clock_add": 1}},
        "narratives": {
            "no_roll": "你让方笙先回去。她没有争辩，只把项目表塞回包里。项目清理时钟向前推进一格，委托仍悬在事务所的桌面上。",
        },
    },
    {
        "id": "commission_details",
        "label": "询问委托细节",
        "aliases": ["问清楚", "了解情况", "问方笙"],
        "location": "OC-01",
        "phases": ["unoffered", "deferred", "active"],
        "requires_clues": [],
        "requires_roll": False,
        "tendency": "共情",
        "modifier": 0,
        "effects": {"no_roll": {}},
        "narratives": {
            "no_roll": "方笙说苗雨的宁证还能显示姓名，却过不了工作和支付验证；三天前她在旧城区晕倒，之后只收到一句自动短讯：‘我很好，不要再找。’",
        },
    },
    {
        "id": "reassure_fangsheng",
        "label": "安抚方笙",
        "aliases": ["安抚方笙", "安慰方笙", "承诺优先确认苗雨安全"],
        "location": "OC-01",
        "phases": ["active"],
        "requires_clues": ["commission"],
        "requires_roll": False,
        "tendency": "共情",
        "modifier": 0,
        "effects": {"no_roll": {}},
        "narratives": {
            "no_roll": "你承诺优先确认苗雨安全。方笙绷紧的肩膀稍稍放松，答应整理旧排班里没来得及说明的备注。",
        },
    },
    {
        "id": "travel_hc07",
        "label": "前往新栖公寓",
        "aliases": ["去新栖公寓", "前往蜂巢区", "去方笙住处"],
        "location": "OC-01",
        "phases": ["active"],
        "requires_clues": ["commission"],
        "requires_roll": False,
        "tendency": "行动",
        "modifier": 0,
        "effects": {"no_roll": {"location_to": "HC-07"}},
        "narratives": {
            "no_roll": "你穿过雨雾进入蜂巢区。新栖公寓的电梯面板把共享居住、外包项目和门禁权限压在同一层楼里。",
        },
    },
    {
        "id": "travel_oc03",
        "label": "前往青苔诊所",
        "aliases": ["去青苔诊所", "前往诊所", "找林砚舟"],
        "location": "OC-01",
        "phases": ["active"],
        "requires_clues": ["commission"],
        "requires_roll": False,
        "tendency": "行动",
        "modifier": 0,
        "effects": {"no_roll": {"location_to": "OC-03"}},
        "narratives": {
            "no_roll": "青苔诊所的夜诊灯还亮着。林砚舟正在整理匿名编号病历，他不愿替患者作不存在的保证。",
        },
    },
    {
        "id": "travel_lg05",
        "label": "前往白绳货运场",
        "aliases": ["去白绳货运", "前往货运场", "查短驳记录"],
        "location": "*",
        "phases": ["active"],
        "requires_clues": ["anonymous_patient"],
        "requires_roll": False,
        "tendency": "行动",
        "modifier": 0,
        "effects": {"no_roll": {"location_to": "LG-05"}},
        "narratives": {
            "no_roll": "白绳货运场的雨棚下堆满短驳箱。值班员核对签单时很谨慎，他们保护司机，也不愿替别人背锅。",
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
            "no_roll": "你回到事务所。唐葵已经把新拿到的材料别到案件板上，等你决定下一步。",
        },
    },
    {
        "id": "inspect_fangsheng_room",
        "label": "查看方笙住处",
        "aliases": ["检查住处", "查看房间", "看苗雨痕迹"],
        "location": "HC-07",
        "phases": ["active"],
        "requires_clues": ["commission"],
        "requires_roll": True,
        "tendency": "洞察",
        "modifier": 1,
        "effects": {
            "success": {"clues_add": ["fangsheng_present"]},
            "partial": {"clues_add": ["fangsheng_present"], "clock_add": 1},
            "escalation": {"clues_add": ["fangsheng_present"], "clock_add": 1},
        },
        "narratives": {
            "success": "方笙住处还留着苗雨的漱口杯、工牌套和半盒代餐。她不是被凭空编造出来的人。",
            "partial": "你找到了苗雨留下的生活痕迹，但花了太多时间，楼里的项目终端正在同步清理。",
            "escalation": "你确认了苗雨真实生活过的痕迹，同时听见走廊里有人正在删除本地排班。",
        },
    },
    {
        "id": "request_project_export",
        "label": "要求查看项目导出",
        "aliases": ["查看项目导出", "导出项目表", "要工作量记录"],
        "location": "HC-07",
        "phases": ["active"],
        "requires_clues": ["commission"],
        "requires_roll": True,
        "tendency": "技术",
        "modifier": 1,
        "effects": {
            "success": {"clues_add": ["project_export"]},
            "partial": {"clues_add": ["project_export"], "clock_add": 1},
            "escalation": {"clues_add": ["export_delayed"], "clock_add": 1},
        },
        "narratives": {
            "success": "项目导出里同一批生产账户对应着远超正式名单的工作量，苗雨的名字夹在共享凭证后面。",
            "partial": "你拿到了导出，也看见了超额账户；但邵谦已经把部分本地表同步到云端。",
            "escalation": "导出被推迟，不过缓存里仍能看出账户关系异常，足够继续往下查。",
        },
    },
    {
        "id": "check_shared_account",
        "label": "核对共享排班",
        "aliases": ["看共享账户", "核对排班", "查共享凭证"],
        "location": "HC-07",
        "phases": ["active"],
        "requires_clues": [],
        "requires_clues_any": ["project_export", "export_delayed"],
        "requires_roll": True,
        "tendency": "洞察",
        "modifier": 0,
        "effects": {
            "success": {"clues_add": ["shared_account"]},
            "partial": {"clues_add": ["shared_account"], "clock_add": 1},
            "escalation": {"clues_add": ["risk_warning", "shared_account"], "clock_add": 1},
        },
        "narratives": {
            "success": "排班显示邵谦团队用少数凭证管理大量生产账户，苗雨只是被复用的节点之一。",
            "partial": "你确认了共享排班；项目清理进度又逼近了一格，但证据仍在手里。",
            "escalation": "你翻到一条被忽略的风险警告，也确认共享排班确实存在；局势更紧迫，核心事实没有丢。",
        },
    },
    {
        "id": "confront_shaoqian",
        "label": "当面质问邵谦",
        "aliases": ["找邵谦", "质问邵谦", "和邵谦对峙"],
        "location": "HC-07",
        "phases": ["active"],
        "requires_clues": ["shared_account"],
        "requires_roll": True,
        "tendency": "行动",
        "modifier": 0,
        "effects": {
            "success": {"clues_add": ["shaqian_admission"], "clock_add": 1},
            "partial": {"clues_add": ["shaqian_admission"], "clock_add": 1},
            "escalation": {"clock_add": 2},
        },
        "narratives": {
            "success": "邵谦承认自己仍在使用旧凭证，却把责任推给项目效率和上层指标。",
            "partial": "邵谦松口承认旧凭证仍在运行，但他同时通知了公司清理本地记录。",
            "escalation": "邵谦拒绝正面回答，只留下一句‘你去找公司’。共享排班证据已经足够，不必依赖他。",
        },
    },
    {
        "id": "ask_anonymous_patient",
        "label": "询问匿名患者",
        "aliases": ["查匿名病历", "问林砚舟", "问诊所患者"],
        "location": "OC-03",
        "phases": ["active"],
        "requires_clues": ["commission"],
        "requires_roll": True,
        "tendency": "共情",
        "modifier": 1,
        "effects": {
            "success": {"clues_add": ["anonymous_patient"]},
            "partial": {"clues_add": ["anonymous_patient"], "clock_add": 1},
            "escalation": {"clues_add": ["clinic_hint", "anonymous_patient"], "clock_add": 1},
        },
        "narratives": {
            "success": "林砚舟确认三天前有一名低血糖、惊恐的年轻女性匿名就诊，体征与苗雨相符。",
            "partial": "你确认了匿名就诊记录，但诊所只肯给你有限信息，时间仍在流逝。",
            "escalation": "林砚舟不肯透露更多，却提到患者是乘白绳短驳离开的；核心行踪仍被你拿到。",
        },
    },
    {
        "id": "check_freight_record",
        "label": "查询短驳记录",
        "aliases": ["查货运签", "看短驳记录", "查苗雨货运"],
        "location": "LG-05",
        "phases": ["active"],
        "requires_clues": ["anonymous_patient"],
        "requires_roll": True,
        "tendency": "行动",
        "modifier": 0,
        "effects": {
            "success": {"clues_add": ["freight_manifest"]},
            "partial": {"clues_add": ["freight_manifest"], "clock_add": 1},
            "escalation": {"clues_add": ["manifest_alternative"], "clock_add": 1},
        },
        "narratives": {
            "success": "货运签显示那名匿名乘客前往沉没带，停靠点靠近白鹭滞留区。",
            "partial": "你拿到了货运签，也看见白绳值班员开始删除当天的额外备注。",
            "escalation": "签单残了一角，但离开方向仍是沉没带；你没有失去最关键的行踪证据。",
        },
    },
    {
        "id": "contact_miaoyu",
        "label": "联系阿洛药摊确认苗雨",
        "aliases": ["联系苗雨", "找阿洛", "联系阿洛"],
        "location": "LG-05",
        "phases": ["active"],
        "requires_clues": [],
        "requires_clues_any": ["freight_manifest", "manifest_alternative"],
        "requires_roll": True,
        "tendency": "共情",
        "modifier": 1,
        "effects": {
            "success": {"clues_add": ["miaoyu_alive"]},
            "partial": {"clues_add": ["miaoyu_alive"], "clock_add": 1},
            "escalation": {"clues_add": ["miaoyu_alive"], "clock_add": 1},
        },
        "narratives": {
            "success": "阿洛传来一段语音：苗雨还活着，暂时替药摊整理纸质记录，她不想立刻被带回临潮。",
            "partial": "你确认苗雨仍在世，但白绳那边也开始追问是谁在查这条短驳线。",
            "escalation": "苗雨没有直接回应，但阿洛证明她安全。人还活着，只是不愿被制度和公司找到。",
        },
    },
    {
        "id": "end_personal_review",
        "label": "选择低调个人复核",
        "aliases": ["低调复核", "帮苗雨个人恢复", "个人和解"],
        "location": "*",
        "phases": ["active"],
        "requires_clues": ["miaoyu_alive"],
        "requires_clues_any": ["shared_account", "project_export", "export_delayed"],
        "requires_roll": False,
        "tendency": "共情",
        "modifier": 0,
        "effects": {"no_roll": {"phase_to": "closed", "ending": "personal_review"}},
        "narratives": {
            "no_roll": "你只提交足够证明苗雨真实存在和身份异常的材料。她低调恢复部分权限，邵谦与数澜的系统性做法暂时没有被公开撕开。",
        },
    },
    {
        "id": "end_collective_review",
        "label": "提交集体证据",
        "aliases": ["集体复核", "公开共享账户", "提交证据"],
        "location": "*",
        "phases": ["active"],
        "requires_clues": ["miaoyu_alive", "shared_account", "project_export"],
        "requires_roll": False,
        "tendency": "行动",
        "modifier": 0,
        "effects": {"no_roll": {"phase_to": "closed", "ending": "collective_review"}},
        "narratives": {
            "no_roll": "你把共享排班、项目导出和苗雨仍在世的证据一并递交。这会迫使平台面对幽灵劳动，也把更多借证工人推到台前。",
        },
    },
    {
        "id": "end_stop_tracing",
        "label": "尊重苗雨意愿，停止追查",
        "aliases": ["不找回她", "停止追查", "尊重苗雨"],
        "location": "*",
        "phases": ["active"],
        "requires_clues": ["miaoyu_alive"],
        "requires_roll": False,
        "tendency": "共情",
        "modifier": 0,
        "effects": {"no_roll": {"phase_to": "closed", "ending": "stop_tracing"}},
        "narratives": {
            "no_roll": "你确认苗雨安全后选择不再逼她回来。案件以人还活着、身份仍悬而未决结束，唐葵把这页先压在案件板最下面。",
        },
    },
]

# 只有明确声明的移动、调查和社交行动消耗一点游戏内时间。
TIME_COST_ACTIONS = {
    "travel_hc07", "travel_oc03", "travel_lg05", "travel_oc01",
    "inspect_fangsheng_room", "request_project_export", "check_shared_account",
    "confront_shaoqian", "ask_anonymous_patient", "check_freight_record",
    "contact_miaoyu", "reassure_fangsheng",
}
for _action in ACTIONS:
    if _action["id"] in TIME_COST_ACTIONS:
        _action["time_cost"] = 1
