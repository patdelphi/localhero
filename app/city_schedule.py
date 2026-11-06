"""程序说明：定义城市切片时段、十二名持续 NPC 的固定日程与有界离屏摘要。

日程以行动节拍推进：每提交一次行动，案件状态 revision 加一，城市时间前进一个时段。
本模块只派生玩家可见的位置与公开活动，不写入认知记录，也不新增隐藏事实。
"""

# 一天四段；版本 0 对应第一日清晨。
SLOT_LABELS = ("清晨", "白天", "傍晚", "夜间")
SLOTS_PER_DAY = len(SLOT_LABELS)
# 单次离屏事件最多记录的公开条目数，保证写入量有界。
MAX_OFFSCREEN_ITEMS = 3

# 城市切片地点：案件内地点沿用既有编号，另补少量仅用于展示的常驻地点。
CITY_LOCATIONS = {
    "OC-01": ("灰区事务所", "旧城区"),
    "OC-02": ("春兰小馆", "旧城区"),
    "OC-03": ("青苔诊所", "旧城区"),
    "OC-04": ("永安里", "旧城区"),
    "OC-05": ("旧城区派出所", "旧城区"),
    "OC-06": ("九号修理铺", "旧城区"),
    "OC-07": ("联合服务点", "旧城区"),
    "HC-01": ("栖光里商业综合体", "蜂巢区"),
    "HC-02": ("栖光里社区学校", "蜂巢区"),
    "HC-04": ("零工互助站", "蜂巢区"),
    "HC-07": ("新栖公寓", "蜂巢区"),
    "HC-09": ("安澜工程调度点", "蜂巢区"),
    "LG-05": ("白绳货运场", "老港区"),
}


def _slot(location: str, activity: str, visibility: str = "public") -> dict:
    """构造单条日程；visibility 决定是否会出现在玩家可见面板。"""
    return {"location": location, "activity": activity, "visibility": visibility}


# 十二名持续 NPC 的固定顺序，同时决定位置面板排序与离屏事件轮转顺序。
NPC_ORDER = (
    ("lin_yanzhou", "林砚舟"),
    ("xu_chunlan", "许春兰"),
    ("liang_jiu", "梁九"),
    ("luo_qiming", "罗启明"),
    ("chen_huai", "陈槐"),
    ("wei_shuzhen", "魏淑珍"),
    ("zhou_mi", "周弥"),
    ("fang_sheng", "方笙"),
    ("gu_beiting", "顾北庭"),
    ("han_lu", "韩鹭"),
    ("qiao_zhi", "乔稚"),
    ("shen_jianwei", "沈见微"),
)

# 每名 NPC 的四段固定日程；私密条目不会进入玩家视图，也不生成公开摘要。
SCHEDULES = {
    "lin_yanzhou": [
        _slot("OC-03", "整理夜诊记录"),
        _slot("OC-03", "接诊"),
        _slot("OC-04", "给独居老人送药"),
        _slot("OC-03", "值夜"),
    ],
    "xu_chunlan": [
        _slot("OC-02", "备餐"),
        _slot("OC-02", "营业"),
        _slot("OC-02", "营业"),
        _slot("OC-02", "打烊算账"),
    ],
    "liang_jiu": [
        _slot("OC-06", "修理旧终端"),
        _slot("OC-06", "营业"),
        _slot("OC-03", "上门维修医疗设备"),
        _slot("OC-06", "整理零件"),
    ],
    "luo_qiming": [
        _slot("OC-05", "交接班"),
        _slot("OC-04", "巡查"),
        _slot("OC-05", "处理纠纷"),
        _slot("OC-05", "值班"),
    ],
    "chen_huai": [
        _slot("OC-07", "整理卷宗"),
        _slot("OC-07", "接待来访"),
        _slot("OC-07", "复核材料"),
        _slot("OC-07", "加班", "private"),
    ],
    "wei_shuzhen": [
        _slot("OC-04", "核对居民清册"),
        _slot("OC-04", "走访住户"),
        _slot("OC-02", "和许春兰吃饭"),
        _slot("OC-04", "整理手写表格"),
    ],
    "zhou_mi": [
        _slot("HC-04", "分拣互助记录"),
        _slot("HC-01", "接单配送"),
        _slot("HC-04", "互助会值班"),
        _slot("HC-01", "夜班配送"),
    ],
    "fang_sheng": [
        _slot("HC-07", "补记清洁任务"),
        _slot("HC-07", "远程清洁"),
        _slot("HC-04", "找周弥核对记录"),
        _slot("HC-07", "夜班", "private"),
    ],
    "gu_beiting": [
        _slot("HC-09", "交接工单"),
        _slot("HC-01", "巡查设备"),
        _slot("HC-09", "处理投诉"),
        _slot("HC-01", "应急值守"),
    ],
    "han_lu": [
        _slot("HC-04", "修旧终端"),
        _slot("HC-04", "换配件"),
        _slot("HC-07", "上门维修"),
        _slot("HC-04", "接私单", "private"),
    ],
    "qiao_zhi": [
        _slot("HC-02", "备课"),
        _slot("HC-02", "上课"),
        _slot("HC-02", "家长会"),
        _slot("HC-07", "回家"),
    ],
    "shen_jianwei": [
        _slot("HC-01", "内部会议", "private"),
        _slot("HC-09", "查看调度记录", "private"),
        _slot("HC-01", "处理事故报告", "private"),
        _slot("HC-09", "夜间核查", "private"),
    ],
}


def city_time(revision: int) -> dict:
    """把行动版本换算成第几日与时段；版本 0 为第一日清晨。"""
    try:
        value = int(revision or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("行动版本必须是整数") from exc
    if value < 0:
        raise ValueError("行动版本不能为负数")
    slot_index = value % SLOTS_PER_DAY
    return {
        "revision": value,
        "day": value // SLOTS_PER_DAY + 1,
        "slot_index": slot_index,
        "slot_label": SLOT_LABELS[slot_index],
    }


def positions(revision: int) -> list[dict]:
    """返回当前时段玩家可见的 NPC 位置；私密行程直接排除。"""
    slot_index = city_time(revision)["slot_index"]
    result = []
    for npc_id, name in NPC_ORDER:
        entry = SCHEDULES[npc_id][slot_index]
        if entry["visibility"] != "public":
            continue
        location_name, district = CITY_LOCATIONS[entry["location"]]
        result.append(
            {
                "npc_id": npc_id,
                "name": name,
                "location_id": entry["location"],
                "location_name": location_name,
                "district": district,
                "activity": entry["activity"],
                "visibility": entry["visibility"],
            }
        )
    return result


def build_offscreen_payload(revision: int) -> dict | None:
    """轮转选取最多三条公开活动，生成单条有界离屏事件负载。

    同一版本必然得到相同负载，因此回放可确定性复现；私密条目不会入选。
    """
    time_info = city_time(revision)
    slot_index = time_info["slot_index"]
    public_npcs = [
        (npc_id, name)
        for npc_id, name in NPC_ORDER
        if SCHEDULES[npc_id][slot_index]["visibility"] == "public"
    ]
    if not public_npcs:
        return None
    # 以版本为起点轮转，让不同时段摘要不同，同时保持完全确定。
    start = time_info["revision"] % len(public_npcs)
    picked = [
        public_npcs[(start + offset) % len(public_npcs)]
        for offset in range(min(MAX_OFFSCREEN_ITEMS, len(public_npcs)))
    ]
    items = []
    for npc_id, name in picked:
        entry = SCHEDULES[npc_id][slot_index]
        location_name, district = CITY_LOCATIONS[entry["location"]]
        items.append(
            {
                "npc_id": npc_id,
                "name": name,
                "location_id": entry["location"],
                "location_name": location_name,
                "district": district,
                "activity": entry["activity"],
                "visibility": entry["visibility"],
            }
        )
    return {
        "day": time_info["day"],
        "slot_index": slot_index,
        "slot_label": time_info["slot_label"],
        "items": items,
    }
