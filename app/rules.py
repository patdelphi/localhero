"""程序说明：提供公开 2D6 判定、结果分档和按序号复现的机械随机。"""

from dataclasses import dataclass
import random


@dataclass(frozen=True)
class RollResult:
    """保存一次已经发生的机械判定，模型不能修改这些字段。"""

    dice: tuple[int, int]
    modifier: int
    outcome: str

    @property
    def total(self) -> int:
        """计算骰点与修正值的总和。"""
        return sum(self.dice) + self.modifier

    def to_dict(self) -> dict:
        """转换为可持久化和前端展示的字典。"""
        return {
            "dice": list(self.dice),
            "modifier": self.modifier,
            "total": self.total,
            "outcome": self.outcome,
        }


def classify_roll(total: int) -> str:
    """按设计文档划分成功、有代价成功和局势升级。"""
    if total >= 10:
        return "success"
    if total >= 7:
        return "partial"
    return "escalation"


def roll_2d6(modifier: int, rng: random.Random) -> RollResult:
    """使用传入的随机源掷两枚六面骰，便于测试复现。"""
    dice = (rng.randint(1, 6), rng.randint(1, 6))
    total = sum(dice) + modifier
    return RollResult(dice=dice, modifier=modifier, outcome=classify_roll(total))


def roll_for_sequence(seed: int, sequence: int, modifier: int) -> RollResult:
    """按存档种子和判定序号生成独立随机流，读取存档后仍可复现。"""
    return roll_2d6(modifier, random.Random(f"{seed}:{sequence}"))
