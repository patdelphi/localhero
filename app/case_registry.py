"""程序说明：汇总各案件的固定内容，供存档按 case_id 加载。

C01 继续使用 case_content 模块，本模块只做包装；C02 内容位于 case_c02。
"""

from dataclasses import dataclass
from types import ModuleType
from typing import Callable

from app import case_c02, case_content

DEFAULT_CASE_ID = "C01"


@dataclass
class CaseBundle:
    """一个案件的全部固定内容与元数据，实例在进程内共享且只读使用。"""

    module: ModuleType
    case_id: str
    title: str
    subtitle: str
    content_version: str
    start_phase: str
    start_location: str
    opening: str
    clock_id: str
    clock_label: str
    clock_max: int
    plan_scope: str
    commission_clue: str | None
    commission_action: str
    locations: dict
    clue_labels: dict
    clue_definitions: dict
    actions: tuple
    action_metadata: dict
    knowledge_declarations: dict
    local_plan_definitions: dict
    npc_initial_knowledge: dict
    autonomy_plan_definitions: dict
    autonomy_effect_definitions: dict
    scene_definitions: list
    endings: dict
    cross_case_links: dict
    initial_cognition: Callable

    def __post_init__(self):
        """建立行动索引，避免每次按编号线性查找。"""
        self.action_index = {action["id"]: action for action in self.actions}

    def action(self, action_id: str) -> dict:
        """按编号读取行动，未知编号抛 KeyError。"""
        return self.action_index[action_id]


def _build_c01() -> CaseBundle:
    """包装 C01 内容；对外元数据保持既有版本与初始状态。"""
    return CaseBundle(
        module=case_content,
        case_id="C01",
        title="不存在的人",
        subtitle="共享账户、灰档与白绳短驳",
        content_version=case_content.CONTENT_VERSION,
        start_phase="unoffered",
        start_location="OC-01",
        opening=(
            "雨敲着事务所的旧窗。唐葵坐在案件板旁，桌上的终端还亮着。"
            "你可以查看现场、检查终端，或和她谈谈。"
        ),
        clock_id="project_cleanup",
        clock_label="项目清理",
        clock_max=4,
        plan_scope="c01",
        commission_clue="commission",
        commission_action="accept_commission",
        locations=case_content.LOCATIONS,
        clue_labels=case_content.CLUE_LABELS,
        clue_definitions=case_content.CLUE_DEFINITIONS,
        actions=tuple(case_content.ACTIONS),
        action_metadata=case_content.ACTION_METADATA,
        knowledge_declarations=case_content.KNOWLEDGE_DECLARATIONS,
        local_plan_definitions=case_content.LOCAL_PLAN_DEFINITIONS,
        npc_initial_knowledge=case_content.NPC_INITIAL_KNOWLEDGE,
        autonomy_plan_definitions=case_content.AUTONOMY_PLAN_DEFINITIONS,
        autonomy_effect_definitions=case_content.AUTONOMY_EFFECT_DEFINITIONS,
        scene_definitions=case_content.SCENE_DEFINITIONS,
        endings=case_content.ENDINGS,
        cross_case_links={},
        initial_cognition=case_content.initial_cognition,
    )


def _build_c02() -> CaseBundle:
    """包装 C02 内容；跨案线索只作为元数据随案件暴露。"""
    return CaseBundle(
        module=case_c02,
        case_id=case_c02.CASE_ID,
        title=case_c02.CASE_TITLE,
        subtitle=case_c02.CASE_SUBTITLE,
        content_version=case_c02.CONTENT_VERSION,
        start_phase="unoffered",
        start_location=case_c02.START_LOCATION,
        opening=(
            "雨敲着事务所的旧窗。零工互助会转来一份事故委托："
            "配送员周弥在栖光里被平台封号。你可以先了解细节，或接下这份委托。"
        ),
        clock_id=case_c02.CLOCK_ID,
        clock_label=case_c02.CLOCK_LABEL,
        clock_max=case_c02.CLOCK_MAX,
        plan_scope=case_c02.PLAN_SCOPE,
        commission_clue=case_c02.COMMISSION_CLUE,
        commission_action=case_c02.COMMISSION_ACTION,
        locations=case_c02.LOCATIONS,
        clue_labels=case_c02.CLUE_LABELS,
        clue_definitions=case_c02.CLUE_DEFINITIONS,
        actions=tuple(case_c02.ACTIONS),
        action_metadata=case_c02.ACTION_METADATA,
        knowledge_declarations=case_c02.KNOWLEDGE_DECLARATIONS,
        local_plan_definitions=case_c02.LOCAL_PLAN_DEFINITIONS,
        npc_initial_knowledge=case_c02.NPC_INITIAL_KNOWLEDGE,
        autonomy_plan_definitions=case_c02.AUTONOMY_PLAN_DEFINITIONS,
        autonomy_effect_definitions=case_c02.AUTONOMY_EFFECT_DEFINITIONS,
        scene_definitions=case_c02.SCENE_DEFINITIONS,
        endings=case_c02.ENDINGS,
        cross_case_links=case_c02.CROSS_CASE_LINKS,
        initial_cognition=case_c02.initial_cognition,
    )


# 进程内只构建一次；内容模块是常量，不存在热更新需求。
_CASES: dict[str, CaseBundle] = {
    "C01": _build_c01(),
    "C02": _build_c02(),
}


def get_case(case_id: str | None) -> CaseBundle:
    """按编号读取案件，缺失按 C01；未知编号抛 ValueError。"""
    key = case_id or DEFAULT_CASE_ID
    bundle = _CASES.get(key)
    if bundle is None:
        raise ValueError(f"未知案件：{key}")
    return bundle


def default_case() -> CaseBundle:
    """返回默认案件 C01，供未显式传参的旧调用使用。"""
    return _CASES[DEFAULT_CASE_ID]


def list_cases() -> list[dict]:
    """返回新档界面需要的案件目录，不含隐藏真相。"""
    result = []
    for bundle in _CASES.values():
        result.append(
            {
                "case_id": bundle.case_id,
                "title": bundle.title,
                "subtitle": bundle.subtitle,
                "content_version": bundle.content_version,
                "locations": len(bundle.locations),
                "endings": list(bundle.endings.values()),
                "cross_case": len(bundle.cross_case_links),
            }
        )
    return result


def case_id_for_game(db, game_id: str) -> str:
    """读取存档所属案件；旧档缺列或空值按 C01，存档不存在抛 KeyError。"""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT case_id FROM games WHERE id=?", (game_id,)
        ).fetchone()
    if row is None:
        raise KeyError("存档不存在")
    return row["case_id"] or DEFAULT_CASE_ID


def case_for_game(db, game_id: str) -> CaseBundle:
    """读取存档案件内容；未知编号说明存档内容版本异常。"""
    return get_case(case_id_for_game(db, game_id))
