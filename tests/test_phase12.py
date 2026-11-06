"""程序说明：第十二阶段分支存档、软删除归档与分支回放测试。"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.branching import MAX_BRANCHES
from app.game import GameService
from app.main import create_app
from app.model import SimulatedModel
from app.store import Database


def make_service(tmp_path):
    """只使用临时数据库，避免触碰真实存档。"""
    db = Database(tmp_path / "phase12.db").initialize()
    return GameService(db, SimulatedModel()), db


def act(service, game_id, text, index, action_id):
    """使用显式行动编号，保证测试可重复。"""
    return service.act(game_id, text, f"p12-{index}", action_id)


def latest_action_id(db, game_id):
    """读取最近提交的行动编号；行动表按 rowid 递增。"""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id FROM actions WHERE game_id=? ORDER BY rowid DESC LIMIT 1",
            (game_id,),
        ).fetchone()
    return row["id"]


def action_ids(db, game_id):
    """按提交顺序返回行动编号；分支存档使用重放生成的新编号。"""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id FROM actions WHERE game_id=? ORDER BY rowid", (game_id,)
        ).fetchall()
    return [row["id"] for row in rows]


def play_three(service, db, game_id):
    """完成三次行动，返回三次行动编号，供分叉使用。"""
    steps = (
        ("询问委托细节", "commission_details"),
        ("接受方笙的委托", "accept_commission"),
        ("前往新栖公寓", "travel_hc07"),
    )
    action_ids = []
    for index, (text, action_id) in enumerate(steps, 1):
        act(service, game_id, text, index, action_id)
        action_ids.append(latest_action_id(db, game_id))
    return action_ids


def source_fingerprint(db, game_id):
    """记录源存档的关键行，用于验证分叉全程未修改原存档。"""
    state = db.get_case_state(game_id)
    return {
        "phase": state["phase"],
        "location": state["location"],
        "clock": state["clock"],
        "revision": state["revision"],
        "clues": tuple(state["clues"]),
        "actions": db.count_actions(game_id),
        "events": tuple(
            (event["kind"], event["action_id"]) for event in db.get_events(game_id)
        ),
        "facts": tuple(
            (fact["fact_id"], fact["fact_kind"], fact["visibility"], fact["status"])
            for fact in db.get_case_facts(game_id)
        ),
    }


def test_v7_database_gains_branch_columns_with_backup(tmp_path):
    """v7 存档升级到 v8 时补分支元数据并保留备份。"""
    path = tmp_path / "upgrade.db"
    database = Database(path).initialize()
    with database.connect() as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("ALTER TABLE games DROP COLUMN branch_status")
        conn.execute("ALTER TABLE games DROP COLUMN branch_created_at")
        conn.execute("ALTER TABLE games DROP COLUMN branch_label")
        conn.execute("ALTER TABLE games DROP COLUMN fork_action_index")
        conn.execute("ALTER TABLE games DROP COLUMN fork_action_id")
        conn.execute("ALTER TABLE games DROP COLUMN parent_game_id")
        conn.execute("PRAGMA user_version=7")

    database.initialize()
    with database.connect() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(games)").fetchall()
        }
    assert version == 8
    assert {
        "parent_game_id", "fork_action_id", "fork_action_index",
        "branch_label", "branch_status", "branch_created_at",
    } <= columns
    assert path.with_name(path.name + ".pre-v8.bak").exists()


def test_branch_rebuilds_prefix_state_without_touching_source(tmp_path):
    """分叉重建到指定行动后的状态，源存档关键行完全不变。"""
    service, db = make_service(tmp_path)
    root_id = service.create_game("江逢")["id"]
    actions = play_three(service, db, root_id)
    before = source_fingerprint(db, root_id)

    branch = service.create_branch(root_id, actions[1], "回到接案")
    assert branch["parent_game_id"] == root_id
    assert branch["fork_action_id"] == actions[1]
    assert branch["fork_action_index"] == 2
    assert branch["branch_label"] == "回到接案"
    assert branch["branch_status"] == "active"

    assert db.count_actions(branch["id"]) == 2
    branch_state = db.get_case_state(branch["id"])
    root_state = db.get_case_state(root_id)
    assert branch_state["phase"] == "active"
    assert branch_state["location"] == "OC-01"
    # 只有接案行动改变案件投影，查询委托细节不推进 revision。
    assert branch_state["revision"] == 1
    # 源存档前往了新栖公寓，分支仍停在事务所。
    assert root_state["location"] == "HC-07"
    assert source_fingerprint(db, root_id) == before


def test_branch_actions_do_not_affect_source(tmp_path):
    """分支里继续行动只改变分支，不回写根存档。"""
    service, db = make_service(tmp_path)
    root_id = service.create_game("江逢")["id"]
    actions = play_three(service, db, root_id)
    before = source_fingerprint(db, root_id)
    branch = service.create_branch(root_id, actions[0], "重查")

    act(service, branch["id"], "接受方笙的委托", 10, "accept_commission")
    assert db.count_actions(branch["id"]) == 2
    assert source_fingerprint(db, root_id) == before


def test_branch_replay_matches(tmp_path):
    """分支自身可独立回放并通过校验。"""
    service, db = make_service(tmp_path)
    root_id = service.create_game("江逢")["id"]
    actions = play_three(service, db, root_id)
    branch = service.create_branch(root_id, actions[1], "分支")
    act(service, branch["id"], "前往新栖公寓", 10, "travel_hc07")

    assert service.verify_replay(branch["id"])["status"] == "matched"


def test_branch_tree_lists_nodes_with_state(tmp_path):
    """分支树以根存档为起点，并给出各节点关键状态。"""
    service, db = make_service(tmp_path)
    root_id = service.create_game("江逢")["id"]
    actions = play_three(service, db, root_id)
    branch = service.create_branch(root_id, actions[0], "分支 A")

    tree = service.get_branches(branch["id"])
    assert tree["root_game_id"] == root_id
    assert len(tree["items"]) == 2
    root_item, branch_item = tree["items"]
    assert root_item["is_root"] is True
    assert branch_item["parent_game_id"] == root_id
    assert branch_item["state"]["actions"] == 1
    assert root_item["state"]["actions"] == 3
    assert branch_item["is_current"] is True


def test_branch_from_branch_is_supported(tmp_path):
    """分支可以继续分叉，形成二级节点。"""
    service, db = make_service(tmp_path)
    root_id = service.create_game("江逢")["id"]
    actions = play_three(service, db, root_id)
    first = service.create_branch(root_id, actions[2], "一级")
    # 二级分支必须使用一级分支自身重放后的行动编号，不能复用根存档编号。
    second = service.create_branch(first["id"], action_ids(db, first["id"])[1], "二级")

    tree = service.get_branches(second["id"])
    assert tree["root_game_id"] == root_id
    assert [item["game_id"] for item in tree["items"]] == [
        root_id, first["id"], second["id"],
    ]
    assert second["parent_game_id"] == first["id"]


def test_branch_archive_requires_confirm_and_can_restore(tmp_path):
    """归档必须显式确认；归档后数据保留并可恢复。"""
    service, db = make_service(tmp_path)
    root_id = service.create_game("江逢")["id"]
    actions = play_three(service, db, root_id)
    branch = service.create_branch(root_id, actions[2], "待归档")

    with pytest.raises(ValueError):
        service.set_branch_status(branch["id"], "archived", False)

    archived = service.set_branch_status(branch["id"], "archived", True)
    assert archived["branch_status"] == "archived"
    assert db.count_actions(branch["id"]) == 3

    restored = service.set_branch_status(branch["id"], "active", True)
    assert restored["branch_status"] == "active"


def test_root_game_cannot_be_archived(tmp_path):
    """根存档不属于任何分支，不能归档。"""
    service, db = make_service(tmp_path)
    root_id = service.create_game("江逢")["id"]
    with pytest.raises(ValueError):
        service.set_branch_status(root_id, "archived", True)


def test_unknown_fork_action_is_rejected(tmp_path):
    """分叉点必须是该存档已记录的行动。"""
    service, db = make_service(tmp_path)
    root_id = service.create_game("江逢")["id"]
    before_actions = db.count_actions(root_id)
    with pytest.raises(KeyError):
        service.create_branch(root_id, "not-a-real-action", "非法")

    # 失败的分叉不应留下游戏行或派生数据。
    assert db.count_actions(root_id) == before_actions


def test_branch_limit_is_enforced(tmp_path, monkeypatch):
    """直属分支达到上限后拒绝继续创建。"""
    import app.branching as branching

    monkeypatch.setattr(branching, "MAX_BRANCHES", 1)
    service, db = make_service(tmp_path)
    root_id = service.create_game("江逢")["id"]
    actions = play_three(service, db, root_id)
    service.create_branch(root_id, actions[0], "唯一分支")

    with pytest.raises(ValueError):
        service.create_branch(root_id, actions[1], "超限")


def test_branch_api_create_list_archive_restore(tmp_path):
    """分支接口覆盖创建、列表、归档与恢复。"""
    client = TestClient(create_app(tmp_path / "api.db", SimulatedModel()))
    created = client.post("/api/games", json={"protagonist": "江逢"}).json()
    game_id = created["id"]

    steps = (
        ("询问委托细节", "commission_details"),
        ("接受方笙的委托", "accept_commission"),
    )
    action_ids = []
    for index, (text, action_id) in enumerate(steps, 1):
        response = client.post(
            f"/api/games/{game_id}/actions",
            json={"text": text, "action_id": action_id, "request_id": f"p12-api-{index}"},
        )
        assert response.status_code == 200
        loaded = client.get(f"/api/games/{game_id}").json()
        action_ids.append(
            next(
                event["action_id"]
                for event in reversed(loaded["events"])
                if event["kind"] == "action_committed"
            )
        )

    branch = client.post(
        f"/api/games/{game_id}/branches",
        json={"fork_action_id": action_ids[0], "label": "API 分支"},
    )
    assert branch.status_code == 200
    branch_id = branch.json()["game"]["id"]
    assert branch.json()["game"]["branch_label"] == "API 分支"

    tree = client.get(f"/api/games/{game_id}/branches")
    assert tree.status_code == 200
    assert len(tree.json()["items"]) == 2

    # 未确认的归档请求被拒绝。
    rejected = client.post(f"/api/games/{branch_id}/branch/archive", json={"confirm": False})
    assert rejected.status_code == 422

    archived = client.post(f"/api/games/{branch_id}/branch/archive", json={"confirm": True})
    assert archived.json()["game"]["branch_status"] == "archived"

    restored = client.post(f"/api/games/{branch_id}/branch/restore", json={"confirm": True})
    assert restored.json()["game"]["branch_status"] == "active"


def test_invalid_branch_request_returns_validation_error(tmp_path):
    """缺少分叉行动编号时返回 422，而不是创建空分支。"""
    client = TestClient(create_app(tmp_path / "invalid.db", SimulatedModel()))
    game_id = client.post("/api/games", json={"protagonist": "江逢"}).json()["id"]
    response = client.post(f"/api/games/{game_id}/branches", json={"label": "无分叉点"})
    assert response.status_code == 422
