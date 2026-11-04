"""程序说明：验证模拟模型驱动的行动闭环、重复请求和叙事重试。"""

from app.game import GameService
from app.model import SimulatedModel
from app.store import Database


def make_service(tmp_path, model=None):
    """创建使用临时数据库和模拟模型的服务。"""
    db = Database(tmp_path / "game.db").initialize()
    return GameService(db, model or SimulatedModel()), db


def test_action_returns_roll_and_narrative(tmp_path):
    """检查设备必须经过公开判定并生成模拟叙事。"""
    service, _ = make_service(tmp_path)
    game = service.create_game("江逢")

    result = service.act(game["id"], "检查终端", "request-1")

    assert result["status"] == "complete"
    assert result["roll"]["total"] == sum(result["roll"]["dice"]) + 1
    assert result["narrative"]
    assert result["intent"]["kind"] == "inspect_device"


def test_duplicate_request_does_not_create_new_fact(tmp_path):
    """相同请求标识只返回原结果，不重复掷骰或写事件。"""
    service, db = make_service(tmp_path)
    game = service.create_game("江逢")

    first = service.act(game["id"], "检查终端", "request-1")
    second = service.act(game["id"], "检查终端", "request-1")

    assert second == first
    assert db.get_game(game["id"])["roll_count"] == 1
    kinds = [event["kind"] for event in db.get_events(game["id"])]
    assert kinds.count("action_committed") == 1
    assert kinds.count("narrative_completed") == 1


def test_narrative_retry_does_not_roll_again(tmp_path):
    """模拟叙事首次失败后，重试只补文字，不重复机械判定。"""
    model = SimulatedModel(fail_narrative_times=1)
    service, db = make_service(tmp_path, model)
    game = service.create_game("江逢")

    pending = service.act(game["id"], "检查终端", "request-1")
    assert pending["status"] == "narrative_pending"
    roll = pending["roll"]

    completed = service.retry_narrative(game["id"], pending["action_id"])
    assert completed["status"] == "complete"
    assert completed["roll"] == roll
    assert db.get_game(game["id"])["roll_count"] == 1
    kinds = [event["kind"] for event in db.get_events(game["id"])]
    assert kinds.count("action_committed") == 1
    assert kinds.count("narrative_completed") == 1


def test_talking_does_not_force_roll(tmp_path):
    """普通交谈没有有趣失败后果，不强制掷骰。"""
    service, _ = make_service(tmp_path)
    game = service.create_game("江逢")

    result = service.act(game["id"], "和唐葵谈谈", "request-1")

    assert result["intent"]["kind"] == "talk_tang"
    assert result["roll"] is None
