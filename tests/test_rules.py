"""程序说明：验证 2D6 判定边界、修正值和随机种子复现。"""

import random

from app.rules import classify_roll, roll_2d6


def test_classify_roll_boundaries():
    """10 以上成功，7—9 部分成功，其余局势升级。"""
    assert classify_roll(10) == "success"
    assert classify_roll(7) == "partial"
    assert classify_roll(6) == "escalation"


def test_roll_is_reproducible_with_same_seed():
    """相同种子与修正值必须产生相同机械结果。"""
    first = roll_2d6(1, random.Random(42))
    second = roll_2d6(1, random.Random(42))

    assert first.dice == second.dice
    assert first.total == second.total
    assert first.modifier == 1
    assert first.total == sum(first.dice) + 1
    assert first.outcome == classify_roll(first.total)


def test_dice_stay_in_range():
    """每颗骰子都只能落在 1—6。"""
    for seed in range(20):
        result = roll_2d6(0, random.Random(seed))
        assert all(1 <= die <= 6 for die in result.dice)
