"""程序说明：提供无网络、确定性的模拟模型，用于替代 AI Provider 完成闭环测试。"""

from app.case_content import ACTIONS


class SimulationError(RuntimeError):
    """表示可注入的模拟解析或叙事故障。"""


class SimulatedModel:
    """根据固定案件内容和有限关键词生成意图与文字，不掌握游戏事实。"""

    def __init__(self, fail_parse: bool = False, fail_narrative_times: int = 0):
        self.fail_parse = fail_parse
        self.fail_narrative_times = fail_narrative_times

    def stats(self) -> dict:
        """模拟模型不发起网络请求，统计值恒为零。"""
        return {
            "requests": 0,
            "failures": 0,
            "fallbacks": 0,
            "total_ms": 0.0,
            "last_ms": 0.0,
        }

    def parse_action(self, text: str, legal_actions: list[dict] | None = None) -> dict:
        """优先匹配当前地点的合法案件行动；无法识别时回退到通用观察行动。"""
        if self.fail_parse:
            raise SimulationError("模拟模型暂时无法解析行动")

        legal_actions = legal_actions or []
        matched = self._match_legal_action(text, legal_actions)
        if matched:
            return {
                "kind": "case_action",
                "action_id": matched["id"],
                "label": matched["label"],
                "tendency": matched["tendency"],
                "requires_roll": matched["requires_roll"],
                "modifier": matched["modifier"],
            }

        if "唐葵" in text or "谈谈" in text or "聊聊" in text:
            return {
                "kind": "talk_tang",
                "tendency": "共情",
                "requires_roll": False,
                "modifier": 0,
            }
        if "设备" in text or "终端" in text or "修理" in text:
            return {
                "kind": "inspect_device",
                "tendency": "技术",
                "requires_roll": True,
                "modifier": 1,
            }
        if "查看" in text or "检查" in text or "观察" in text or "现场" in text:
            return {
                "kind": "inspect",
                "tendency": "洞察",
                "requires_roll": True,
                "modifier": 1,
            }
        return {
            "kind": "improvise",
            "tendency": "行动",
            "requires_roll": True,
            "modifier": 0,
        }

    def propose_director(self, context: dict) -> dict | None:
        """按公开效果白名单确定性选择一条提案，不生成展示文本。"""
        effects = context.get("可选效果") or []
        if not effects:
            return None
        effect = effects[int(context.get("动作序号", 0)) % len(effects)]
        return {
            "beat_type": "environment_complication",
            "effect_id": effect["effect_id"],
            "target_action": context.get("当前行动编号"),
            "reason": "环境出现新的公开变化。",
            "source": "simulated",
        }

    def narrate(
        self,
        intent: dict,
        roll: dict | None,
        context: dict | None = None,
        previous_narratives: list[str] | None = None,
        action_content: dict | None = None,
    ) -> str:
        """只描述已提交的意图和判定，不创造新的物品、线索或状态。"""
        if self.fail_narrative_times > 0:
            self.fail_narrative_times -= 1
            raise SimulationError("模拟叙事暂时失败")

        kind = intent["kind"]
        if kind == "case_action":
            action = action_content or self._action_by_id(intent["action_id"])
            outcome = roll["outcome"] if roll else "no_roll"
            narratives = action["narratives"]
            return narratives.get(outcome) or next(iter(narratives.values()))
        if kind == "talk_tang":
            return "唐葵把案件板往旁边挪了挪，听完你的来意。她没有替你作决定，只提醒你：先弄清委托人现在最需要什么。"

        outcome_text = {
            "success": "事情比预想顺利，你获得了清楚的观察结果。",
            "partial": "你得到了需要的信息，但耗时比预想更多，事务所的日程随之收紧。",
            "escalation": "情况出现了新的麻烦；你仍保留已确认的事实，但必须重新安排下一步。",
        }[roll["outcome"]]

        if kind == "inspect_device":
            return f"你沿着终端的电源、接口和本地日志逐项检查。{outcome_text}"
        if kind == "inspect":
            return f"你把事务所的出口、桌面和近期使用痕迹重新核对了一遍。{outcome_text}"
        return f"你尝试用行动推进当前处境，程序只记录这次尝试及其判定。{outcome_text}"

    @staticmethod
    def _match_legal_action(text: str, legal_actions: list[dict]) -> dict | None:
        """优先完全匹配行动标签，其次匹配别名关键词，避免误把自由输入映射到错误行动。"""
        for action in legal_actions:
            if text == action["label"]:
                return action
        for action in legal_actions:
            if any(alias in text for alias in action["aliases"]):
                return action
        return None

    @staticmethod
    def _action_by_id(action_id: str) -> dict:
        """从固定案件内容读取叙事模板。"""
        for action in ACTIONS:
            if action["id"] == action_id:
                return action
        raise KeyError("案件行动不存在")
