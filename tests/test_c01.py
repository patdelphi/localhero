"""程序说明：验证 C01 小型完整单案的两条路径、坏骰、拒绝委托、幂等与结案。"""

from app.game import GameService
from app.model import SimulatedModel
from app.store import Database


def make_service(tmp_path, model=None):
    """创建使用临时数据库和模拟模型的服务。"""
    db = Database(tmp_path / "game.db").initialize()
    return GameService(db, model or SimulatedModel()), db


def act(service, game_id, text, index):
    """用稳定请求标识执行一个行动，避免测试中重复请求冲突。"""
    return service.act(game_id, text, f"request-{index}")


def test_labor_path_can_reach_collective_ending(tmp_path):
    """劳动路径和生活路径合并后，可以解锁提交集体证据结局。"""
    service, _ = make_service(tmp_path)
    game = service.create_game("江逢")
    game_id = game["id"]

    act(service, game_id, "接受方笙的委托", 1)
    act(service, game_id, "前往新栖公寓", 2)
    act(service, game_id, "要求查看项目导出", 3)
    act(service, game_id, "核对共享排班", 4)
    act(service, game_id, "返回灰区事务所", 5)
    act(service, game_id, "前往青苔诊所", 6)
    act(service, game_id, "询问匿名患者", 7)
    act(service, game_id, "前往白绳货运场", 8)
    act(service, game_id, "查询短驳记录", 9)
    contact = act(service, game_id, "联系阿洛药摊确认苗雨", 10)
    ending = act(service, game_id, "提交集体证据", 11)

    case = service.get_game(game_id)["case"]
    assert contact["case"]["clues"][-1]["id"] == "miaoyu_alive"
    assert ending["status"] == "complete"
    assert case["phase"] == "closed"
    assert case["ending"] == "提交集体证据"


def test_life_path_can_stop_tracing(tmp_path):
    """只走生活路径也能确认苗雨在世，并选择尊重其意愿。"""
    service, _ = make_service(tmp_path)
    game = service.create_game("江逢")
    game_id = game["id"]

    act(service, game_id, "接受方笙的委托", 1)
    act(service, game_id, "前往青苔诊所", 2)
    act(service, game_id, "询问匿名患者", 3)
    act(service, game_id, "前往白绳货运场", 4)
    act(service, game_id, "查询短驳记录", 5)
    act(service, game_id, "联系阿洛药摊确认苗雨", 6)
    act(service, game_id, "尊重苗雨意愿，停止追查", 7)

    case = service.get_game(game_id)["case"]
    clues = {clue["id"] for clue in case["clues"]}
    assert {"anonymous_patient", "freight_manifest", "miaoyu_alive"} <= clues
    assert case["phase"] == "closed"
    assert case["ending"] == "尊重苗雨意愿，停止追查"


def test_personal_review_ending_is_reachable(tmp_path):
    """第三条结局路径必须能按固定序列复现。"""
    service, _ = make_service(tmp_path)
    game = service.create_game("江逢")
    game_id = game["id"]

    act(service, game_id, "接受方笙的委托", 1)
    act(service, game_id, "前往新栖公寓", 2)
    act(service, game_id, "要求查看项目导出", 3)
    act(service, game_id, "返回灰区事务所", 4)
    act(service, game_id, "前往青苔诊所", 5)
    act(service, game_id, "询问匿名患者", 6)
    act(service, game_id, "前往白绳货运场", 7)
    act(service, game_id, "查询短驳记录", 8)
    act(service, game_id, "联系阿洛药摊确认苗雨", 9)
    ending = act(service, game_id, "选择低调个人复核", 10)

    assert ending["status"] == "complete"
    assert ending["case"]["phase"] == "closed"
    assert ending["case"]["ending"] == "低调个人复核"


def test_decline_advances_clock_and_can_reaccept(tmp_path):
    """拒绝委托会推进项目清理时钟，但委托仍可重新接手。"""
    service, _ = make_service(tmp_path)
    game = service.create_game("江逢")

    declined = act(service, game["id"], "拒绝委托", 1)
    accepted = act(service, game["id"], "接受方笙的委托", 2)

    assert declined["case"]["phase"] == "deferred"
    assert declined["case"]["clock"] == 1
    assert accepted["case"]["phase"] == "active"


def test_bad_roll_does_not_lose_core_labor_clue(tmp_path):
    """坏骰不会让劳动路径的核心共享账户证据永久消失。"""
    service, _ = make_service(tmp_path)
    game = service.create_game("江逢")
    game_id = game["id"]

    act(service, game_id, "接受方笙的委托", 1)
    act(service, game_id, "前往新栖公寓", 2)
    act(service, game_id, "要求查看项目导出", 3)
    act(service, game_id, "核对共享排班", 4)

    clues = {clue["id"] for clue in service.get_game(game_id)["case"]["clues"]}
    assert "shared_account" in clues


def test_duplicate_case_action_does_not_change_state_twice(tmp_path):
    """同一请求标识重复提交不会重复推进案件状态或掷骰。"""
    service, db = make_service(tmp_path)
    game = service.create_game("江逢")

    first = service.act(game["id"], "接受方笙的委托", "same")
    second = service.act(game["id"], "接受方笙的委托", "same")

    assert first == second
    assert db.get_game(game["id"])["roll_count"] == 0
    kinds = [event["kind"] for event in db.get_events(game["id"])]
    assert kinds.count("case_changed") == 1


def test_persistence_preserves_case_state(tmp_path):
    """重新读取存档时，阶段、地点、线索和时钟保持一致。"""
    service, _ = make_service(tmp_path)
    game = service.create_game("江逢")
    game_id = game["id"]

    act(service, game_id, "接受方笙的委托", 1)
    act(service, game_id, "前往新栖公寓", 2)

    case = service.get_game(game_id)["case"]
    assert case["phase"] == "active"
    assert case["location"] == "HC-07"
    assert any(clue["id"] == "commission" for clue in case["clues"])
