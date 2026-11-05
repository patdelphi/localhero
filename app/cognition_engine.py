"""程序说明：以纯函数计算人物认知来源、有效记忆精度和追加纠正，不读写数据库。"""

from copy import deepcopy
import uuid


PRECISIONS = {"unknown", "fragmentary", "vague", "exact"}
PRECISION_RANK = {"unknown": 0, "fragmentary": 1, "vague": 2, "exact": 3}


def effective_precision(record, world_time):
    """返回指定游戏内时间的有效精度；证词保留发言时精度。"""
    precision = record.get("precision", "unknown")
    if precision not in PRECISIONS:
        raise ValueError("认知精度枚举非法")
    if type(world_time) is not int or world_time < 0:
        raise ValueError("世界时间必须是非负整数")
    if record.get("kind") == "testimony" or precision == "unknown":
        return precision
    observed_at = record.get("observed_at")
    if type(observed_at) is not int or observed_at < 0:
        raise ValueError("观察时间必须是非负整数")
    if observed_at > world_time:
        raise ValueError("观察时间不能晚于当前世界时间")
    elapsed = world_time - observed_at
    if elapsed <= 3:
        return precision
    cap = "vague" if elapsed <= 6 else "fragmentary"
    return precision if PRECISION_RANK[precision] < PRECISION_RANK[cap] else cap


def build_cognition_view(holder_id, records, world_time):
    """建立指定持有者的来源、有效精度和纠正投影，不修改输入。"""
    selected = [deepcopy(item) for item in records if item.get("holder_id") == holder_id]
    if len(selected) > 64:
        raise ValueError("单持有者认知来源图超过64个节点上限")
    by_id = {}
    positions = {}
    for index, record in enumerate(selected):
        knowledge_id = record.get("knowledge_id") or record.get("id")
        if not knowledge_id or knowledge_id in by_id:
            raise ValueError("认知记录标识缺失或重复")
        record["knowledge_id"] = knowledge_id
        record["corrected_by"] = []
        by_id[knowledge_id] = record
        physical_id = record.get("id")
        if physical_id is not None and physical_id in by_id and physical_id != knowledge_id:
            raise ValueError("认知记录物理标识重复")
        if physical_id is not None:
            by_id[physical_id] = record
        positions[knowledge_id] = index
        if physical_id is not None:
            positions[physical_id] = index

    for index, record in enumerate(selected):
        source_id = record.get("source_record_id")
        if source_id is not None:
            source = by_id.get(source_id)
            if source is None or source["holder_id"] != holder_id:
                raise ValueError("认知来源必须属于同一持有者")
            if positions[source_id] >= index and record.get("kind") != "observation":
                raise ValueError("认知来源必须早于当前记录")
        target_id = record.get("corrects_record_id")
        if target_id is not None:
            target = by_id.get(target_id)
            if target is None or target["holder_id"] != holder_id:
                raise ValueError("纠正目标必须属于同一持有者")
            if target_id == record["knowledge_id"] or positions[target_id] >= index:
                raise ValueError("纠正目标必须早于当前记录且不能自指")
            if record.get("fact_id") is not None:
                raise ValueError("追加纠正不能授予新的事实")
            target["corrected_by"].append(record["knowledge_id"])
        record["effective_precision"] = effective_precision(record, world_time)

    # 来源与纠正均只能指向较早记录；此处再防御外部输入形成隐蔽环。
    for record in selected:
        seen = set()
        current = record
        while current is not None:
            current_id = current["knowledge_id"]
            if current_id in seen:
                raise ValueError("认知来源图不能成环")
            seen.add(current_id)
            next_id = current.get("source_record_id") or current.get("corrects_record_id")
            current = by_id.get(next_id) if next_id is not None else None
    return selected


def build_declared_cognition(action, outcome, context, after_time):
    """按 C01 固定声明生成主行动的追加认知；未声明时返回空列表。"""
    if action.get("id") != "commission_details" or outcome != "no_roll":
        return []
    view = build_cognition_view(
        "fang_sheng", context.get("knowledge", []), after_time
    )
    source = next(
        (
            item for item in view
            if item["knowledge_id"].endswith(":fang_sheng:last_login_inference")
            or item["knowledge_id"] == "fang_sheng:last_login_inference"
        ),
        None,
    )
    if (
        source is None or source["corrected_by"]
        or source["effective_precision"] not in {"exact", "vague"}
    ):
        return []
    return [{
        "holder_id": "fang_sheng",
        "kind": "testimony",
        "fact_id": None,
        "content": "方笙说：我记得邵谦的凭证最后登录过，所以我怀疑当晚只有邵谦使用凭证。",
        "accuracy": "honest",
        "visibility": "player",
        "source_record_id": source["knowledge_id"],
        "observed_at": None,
        "precision": source["effective_precision"],
        "corrects_record_id": None,
        "reason_codes": ["last_login_overgeneralization"],
    }]


def validate_cognition_changes(changes, context, source_event_order):
    """校验单批认知数量、来源、纠正和事件顺序，返回深拷贝结果。"""
    records = deepcopy(changes)
    if len(records) > 32:
        raise ValueError("单行动认知记录超过32条上限")
    if sum(item.get("corrects_record_id") is not None for item in records) > 8:
        raise ValueError("单行动追加纠正超过8条上限")
    existing = deepcopy(context.get("knowledge", []))
    world_time = context.get("after_time", context.get("case", {}).get("world_time", 0))
    for record in records:
        if record.get("kind") not in {"observation", "memory", "testimony"}:
            raise ValueError("认知记录类型非法")
        if record.get("precision", "unknown") not in PRECISIONS:
            raise ValueError("认知精度枚举非法")
        if record.get("kind") in {"memory", "testimony"}:
            if not record.get("source_record_id") and record.get("precision") != "unknown":
                raise ValueError("新记忆或证词必须有明确认知来源")
    combined = existing + records
    for holder_id in {item.get("holder_id") for item in combined}:
        build_cognition_view(holder_id, combined, world_time)
    # 空映射没有事件序号，不能把纠正与目标的缺失值都当作 0 比较。
    if source_event_order:
        for record in records:
            target_id = record.get("corrects_record_id")
            if target_id is None:
                continue
            target = next(
                (item for item in combined if (item.get("knowledge_id") or item.get("id")) == target_id),
                None,
            )
            if target is not None and source_event_order.get(record.get("id"), 0) <= source_event_order.get(target_id, 0):
                raise ValueError("纠正必须晚于被纠正记录")
    return records


def assign_cognition_ids(records, game_id, action_id):
    """按固定输入生成可重放记录 ID，不消耗随机数。"""
    result = deepcopy(records)
    for index, record in enumerate(result):
        if record.get("id"):
            record["knowledge_id"] = record["id"]
            continue
        key = ":".join((
            game_id or "local", action_id, str(index), record["kind"],
            record.get("source_record_id") or "", record["content"],
        ))
        record["id"] = uuid.uuid5(uuid.NAMESPACE_URL, key).hex
        record["knowledge_id"] = record["id"]
    return result
