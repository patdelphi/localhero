"""程序说明：第十一阶段城市时段、持续 NPC 日程与有界离屏事件测试。"""

import pytest
from fastapi.testclient import TestClient

from app.city_schedule import (
    CITY_LOCATIONS,
    MAX_OFFSCREEN_ITEMS,
    NPC_ORDER,
    SCHEDULES,
    SLOT_LABELS,
    build_offscreen_payload,
    city_time,
    positions,
)
from app.game import GameService
from app.main import create_app
from app.model import SimulatedModel
from app.store import Database


def make_service(tmp_path, model=None):
    """创建只使用临时数据库的服务，避免触碰真实存档。"""
    db = Database(tmp_path / "phase11.db").initialize()
    return GameService(db, model or SimulatedModel()), db


def act(service, game_id, text, index, action_id=None):
    """使用显式行动编号提交，避免模型解析差异影响日程断言。"""
    return service.act(game_id, text, f"p11-{index}", action_id)


def offscreen_events(db, game_id):
    """只取离屏日程事件，便于计数与负载断言。"""
    return [event for event in db.get_events(game_id) if event["kind"] == "offscreen_activity"]


def test_city_time_advances_one_slot_per_action():
    """每提交一次行动推进一个时段，四段构成一日。"""
    assert city_time(0)["day"] == 1
    assert city_time(0)["slot_label"] == SLOT_LABELS[0]
    assert city_time(1)["slot_label"] == SLOT_LABELS[1]
    assert city_time(3)["slot_label"] == SLOT_LABELS[3]
    assert city_time(4)["day"] == 2
    assert city_time(4)["slot_label"] == SLOT_LABELS[0]
    with pytest.raises(ValueError):
        city_time(-1)


def test_schedule_covers_twelve_npcs_with_four_slots():
    """十二名持续 NPC 都有四段日程，且地点都在城市切片内。"""
    assert len(NPC_ORDER) == 12
    assert set(SCHEDULES) == {npc_id for npc_id, _ in NPC_ORDER}
    for entries in SCHEDULES.values():
        assert len(entries) == len(SLOT_LABELS)
        for entry in entries:
            assert entry["location"] in CITY_LOCATIONS
            assert entry["visibility"] in {"public", "private"}
            assert entry["activity"]


def test_positions_are_deterministic_and_public_only():
    """位置面板只返回公开日程，重复调用结果完全一致。"""
    first = positions(0)
    assert first == positions(0)
    assert all(item["visibility"] == "public" for item in first)
    # 沈见微的行程全部为私密，任何时段都不应出现在玩家视图。
    assert all(item["npc_id"] != "shen_jianwei" for slot in range(8) for item in positions(slot))
    assert first[0]["location_name"] == CITY_LOCATIONS[first[0]["location_id"]][0]


def test_positions_change_across_slots():
    """至少一名 NPC 在不同时段变换位置，确保日程真实可读。"""
    morning = {(item["npc_id"], item["location_id"]) for item in positions(0)}
    evening = {(item["npc_id"], item["location_id"]) for item in positions(2)}
    assert morning != evening


def test_offscreen_payload_is_bounded_and_deterministic():
    """离屏摘要只取固定上限的公开条目，同一版本结果一致。"""
    payload = build_offscreen_payload(0)
    assert payload == build_offscreen_payload(0)
    assert payload["day"] == 1
    assert payload["slot_label"] == SLOT_LABELS[0]
    assert 1 <= len(payload["items"]) <= MAX_OFFSCREEN_ITEMS
    for item in payload["items"]:
        assert item["visibility"] == "public"
        assert item["location_id"] in CITY_LOCATIONS


def test_one_offscreen_event_per_action(tmp_path):
    """每次行动只写一条离屏事件，负载条目数有上限。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]

    # 四个不同行动覆盖接案、查看现场与移动，避免重复行动的认知标识冲突。
    steps = (
        ("询问委托细节", "commission_details"),
        ("接受方笙的委托", "accept_commission"),
        ("前往新栖公寓", "travel_hc07"),
        ("查看方笙住处", "inspect_fangsheng_room"),
    )
    for index, (text, action_id) in enumerate(steps, 1):
        act(service, game_id, text, index, action_id)

    events = offscreen_events(db, game_id)
    assert len(events) == len(steps)
    for event in events:
        assert len(event["payload"]["items"]) <= MAX_OFFSCREEN_ITEMS


def test_offscreen_events_do_not_grant_player_knowledge(tmp_path):
    """离屏日程进入事件流，但不会生成玩家认知记录。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]

    steps = (
        ("询问委托细节", "commission_details"),
        ("接受方笙的委托", "accept_commission"),
        ("前往新栖公寓", "travel_hc07"),
    )
    for index, (text, action_id) in enumerate(steps, 1):
        act(service, game_id, text, index, action_id)

    knowledge = service.get_knowledge(game_id)["items"]
    offscreen_texts = {
        item["activity"]
        for event in offscreen_events(db, game_id)
        for item in event["payload"]["items"]
    }
    assert all(
        not any(text in record["content"] for text in offscreen_texts)
        for record in knowledge
    )
    # 认知记录只来自行动声明；离屏事件不得携带 fact_id 或认知字段。
    for event in offscreen_events(db, game_id):
        assert "knowledge" not in event["payload"]
        assert "fact_id" not in event["payload"]


def test_city_api_returns_time_and_public_positions(tmp_path):
    """城市接口返回当前时段、公开位置与最近离屏摘要。"""
    client = TestClient(create_app(tmp_path / "api.db", SimulatedModel()))
    created = client.post("/api/games", json={"protagonist": "江逢", "case_id": "C01"})
    game_id = created.json()["id"]

    city = client.get(f"/api/games/{game_id}/city")
    assert city.status_code == 200
    body = city.json()
    assert body["city"]["day"] == 1
    assert body["city"]["slot_label"] == SLOT_LABELS[0]
    assert body["positions"]
    assert all(item["visibility"] == "public" for item in body["positions"])
    assert body["offscreen"] == []

    client.post(
        f"/api/games/{game_id}/actions",
        json={"text": "询问委托细节", "action_id": "commission_details", "request_id": "p11-api-1"},
    )
    updated = client.get(f"/api/games/{game_id}/city").json()
    assert updated["city"]["slot_label"] == SLOT_LABELS[1]
    assert len(updated["offscreen"]) == 1
    assert len(updated["offscreen"][0]["items"]) <= MAX_OFFSCREEN_ITEMS


def test_replay_matches_with_offscreen_events(tmp_path):
    """含离屏事件的行动历史仍可确定性回放。"""
    service, _ = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]

    act(service, game_id, "接受方笙的委托", 1, "accept_commission")
    act(service, game_id, "询问委托细节", 2, "commission_details")
    act(service, game_id, "前往新栖公寓", 3, "travel_hc07")

    result = service.verify_replay(game_id)
    assert result["status"] == "matched"


def test_city_panel_works_for_both_cases(tmp_path):
    """城市切片与案件无关，C01 与 C02 存档都能读取位置面板。"""
    service, _ = make_service(tmp_path)
    c01_id = service.create_game("江逢")["id"]
    c02_id = service.create_game("江逢", "C02")["id"]

    for game_id in (c01_id, c02_id):
        city = service.get_city(game_id)
        assert city["city"]["day"] == 1
        assert all(item["npc_id"] != "shen_jianwei" for item in city["positions"])
