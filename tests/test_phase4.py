"""程序说明：验证第四阶段初始基线、隔离机械回放、历史时间线、隐私与资源预算。"""

import hashlib
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.action_protocol import RULES_VERSION
from app.case_content import CONTENT_VERSION
from app.game import GameService
from app.main import create_app
from app.model import SimulatedModel
from app.replay_engine import ReplayEngine, canonical_json, compare_snapshots
from app.store import Database


def make_service(tmp_path, model=None):
    """建立只使用临时数据库的第四阶段服务。"""
    db = Database(tmp_path / "phase4.db").initialize()
    return GameService(db, model or SimulatedModel()), db


def act(service, game_id, text, request_id, action_id=None):
    """用稳定请求标识提交真实行动，生成后续回放输入。"""
    return service.act(game_id, text, request_id, action_id=action_id)


def start_social_chain(service, game_id):
    """提交包含公开关系、私密信任、履历与固定计划的两步社交链。"""
    act(service, game_id, "接受方笙的委托", "accept")
    act(service, game_id, "安抚方笙", "reassure", "reassure_fangsheng")


def complete_social_chain(service, game_id):
    """继续到固定计划到期，覆盖局部模拟与同源证词。"""
    start_social_chain(service, game_id)
    act(service, game_id, "前往新栖公寓", "travel")
    act(service, game_id, "查看方笙住处", "inspect")
    act(service, game_id, "要求查看项目导出", "export")


def action_rows(db, game_id):
    """按真实提交顺序读取行动，避免测试依赖审计倒序。"""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM actions WHERE game_id=? ORDER BY rowid", (game_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def database_hash(path):
    """计算临时原档主文件哈希，核对回放没有写入。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v5_baseline_is_canonical_and_new_game_is_atomic(tmp_path):
    """基线须与新档同事务写入，哈希稳定，基线失败不得留下半个新档。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 8
        baseline = conn.execute(
            "SELECT * FROM replay_baselines WHERE game_id=?", (game_id,)
        ).fetchone()
    snapshot = json.loads(baseline["snapshot_json"])
    assert baseline["snapshot_json"] == canonical_json(snapshot)
    assert baseline["snapshot_hash"] == hashlib.sha256(
        baseline["snapshot_json"].encode("utf-8")
    ).hexdigest()
    assert baseline["snapshot_format"] == 1
    assert baseline["rules_version"] == RULES_VERSION
    assert baseline["content_version"] == CONTENT_VERSION
    assert snapshot["game"] == {
        "protagonist": "江逢", "location": "OC-01", "seed": 20261103, "roll_count": 0,
    }
    assert snapshot["case"]["revision"] == 0
    assert all(snapshot[key] == [] for key in (
        "facts", "clock_changes", "knowledge", "social_states",
        "character_history", "local_plans",
    ))

    with db.transaction() as conn:
        conn.execute(
            """
            CREATE TRIGGER reject_baseline BEFORE INSERT ON replay_baselines
            BEGIN SELECT RAISE(ABORT, '测试基线失败'); END
            """
        )
    with pytest.raises(sqlite3.IntegrityError, match="测试基线失败"):
        service.create_game("唐葵")
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM case_states").fetchone()[0] == 1


def test_v4_migration_only_adds_structure_and_preserves_history(tmp_path):
    """v4 旧档升级只增加基线表和备份，不伪造基线或改写历史。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    start_social_chain(service, game_id)
    with db.transaction() as conn:
        conn.execute("DROP TABLE replay_baselines")
        conn.execute("PRAGMA user_version=4")
        before = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("games", "actions", "events", "case_states", "social_states")
        }
        revision = conn.execute(
            "SELECT revision FROM case_states WHERE game_id=?", (game_id,)
        ).fetchone()[0]

    Database(db.path).initialize()
    backup = db.path.with_name(f"{db.path.name}.pre-v5.bak")
    assert backup.exists()
    backup_bytes = backup.read_bytes()
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 8
        after = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in before
        }
        assert after == before
        assert conn.execute(
            "SELECT revision FROM case_states WHERE game_id=?", (game_id,)
        ).fetchone()[0] == revision
        assert conn.execute("SELECT COUNT(*) FROM replay_baselines").fetchone()[0] == 0
    Database(db.path).initialize()
    assert backup.read_bytes() == backup_bytes
    result = ReplayEngine(db).verify(game_id)
    assert result["status"] == "unavailable"
    assert result["reason"]["code"] == "baseline_missing"


def test_complete_social_chain_replays_without_model_random_or_source_writes(
    tmp_path, monkeypatch
):
    """完整社交链只用保存输入和骰点即可一致重算，原档字节保持不变。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    complete_social_chain(service, game_id)
    before_hash = database_hash(db.path)
    before_counts = (
        len(action_rows(db, game_id)), len(db.get_events(game_id)),
        db.get_case_state(game_id)["revision"], db.get_game(game_id)["roll_count"],
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("回放不得调用模型或随机数")

    monkeypatch.setattr("app.game.roll_for_sequence", forbidden)
    monkeypatch.setattr("app.model.SimulatedModel.parse_action", forbidden)
    monkeypatch.setattr("app.model.SimulatedModel.narrate", forbidden)
    result = ReplayEngine(db).verify(game_id)

    assert result["status"] == "matched"
    assert result["checked_actions"] == 5
    assert database_hash(db.path) == before_hash
    assert before_counts == (
        len(action_rows(db, game_id)), len(db.get_events(game_id)),
        db.get_case_state(game_id)["revision"], db.get_game(game_id)["roll_count"],
    )


@pytest.mark.parametrize("ending_action", [
    "提交集体证据", "选择低调个人复核", "尊重苗雨意愿，停止追查",
])
def test_all_endings_replay_to_matched(tmp_path, ending_action):
    """三种结局路径均可由保存命令和骰点确定性复现。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    steps = [
        "接受方笙的委托", "前往新栖公寓", "要求查看项目导出", "核对共享排班",
        "返回灰区事务所", "前往青苔诊所", "询问匿名患者", "前往白绳货运场",
        "查询短驳记录", "联系阿洛药摊确认苗雨", ending_action,
    ]
    if ending_action != "提交集体证据":
        steps.remove("核对共享排班")
    for index, text in enumerate(steps):
        act(service, game_id, text, f"step-{index}")
    result = ReplayEngine(db).verify(game_id)
    assert result["status"] == "matched"
    assert result["checked_actions"] == len(steps)


def test_pending_narrative_zero_time_preview_and_hypotheses_do_not_change_replay(tmp_path):
    """叙事待重试和零耗时行动参与同一机械历史，预览与假设不产生回放输入。"""
    model = SimulatedModel(fail_narrative_times=1)
    service, db = make_service(tmp_path, model)
    game_id = service.create_game("江逢")["id"]
    pending = act(service, game_id, "接受方笙的委托", "accept")
    assert pending["status"] == "narrative_pending"
    service.preview_action(game_id, "询问委托细节", "commission_details")
    act(service, game_id, "询问委托细节", "details")
    hypothesis = service.create_hypothesis(game_id, "只记录玩家推理")
    service.update_hypothesis(game_id, hypothesis["id"], "修改私人假设")
    service.delete_hypothesis(game_id, hypothesis["id"])
    first = ReplayEngine(db).verify(game_id)
    second = ReplayEngine(db).verify(game_id)
    assert first["status"] == second["status"] == "matched"
    assert first["checked_actions"] == second["checked_actions"] == 2
    service.retry_narrative(game_id, pending["action_id"])
    assert ReplayEngine(db).verify(game_id)["status"] == "matched"


@pytest.mark.parametrize("sql,path", [
    ("UPDATE games SET location='LG-05' WHERE id=?", "game.location"),
    ("UPDATE games SET roll_count=99 WHERE id=?", "game.roll_count"),
    ("UPDATE case_states SET clock=3 WHERE game_id=?", "case.clock"),
    ("UPDATE case_facts SET mechanical_json='{}' WHERE game_id=? AND fact_id='commission'", "facts.commission.mechanical.grants_action_permission"),
    ("UPDATE clock_changes SET after_value=9 WHERE game_id=?", "clock_changes[0].after_value"),
    ("UPDATE knowledge_records SET content='篡改认知' WHERE game_id=?", "knowledge[0].content"),
    ("UPDATE social_states SET value_text='篡改关系' WHERE game_id=? AND kind='relationship'", "social_states.fang_sheng:player:relationship.value_text"),
    ("UPDATE character_history SET content='篡改履历' WHERE game_id=? AND visibility='public'", "character_history[0].content"),
    ("UPDATE local_plans SET due_time=99 WHERE game_id=?", "local_plans.fangsheng_followup.due_time"),
])
def test_each_public_domain_tamper_is_located(tmp_path, sql, path):
    """当前投影或历史记录被篡改时，应在对应字段报告首个不一致。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    if "clock_changes" in sql:
        act(service, game_id, "拒绝委托", "decline")
    else:
        start_social_chain(service, game_id)
    with db.transaction() as conn:
        conn.execute(sql, (game_id,))
    result = ReplayEngine(db).verify(game_id)
    assert result["status"] == "mismatched"
    assert result["first_mismatch"]["action_index"] >= 1
    assert any(item["path"] == path for item in result["first_mismatch"]["differences"])


def test_private_only_mismatch_is_redacted_by_api(tmp_path):
    """私密信任参与内部比较，但 API 不得泄露标识、精确值或记忆内容。"""
    client = TestClient(create_app(tmp_path / "private.db", model=SimulatedModel()))
    service = client.app.state.service
    game_id = client.post("/api/games", json={"protagonist": "江逢"}).json()["id"]
    start_social_chain(service, game_id)
    with service.db.transaction() as conn:
        conn.execute(
            "UPDATE social_states SET value_int=2 WHERE game_id=? AND kind='trust'",
            (game_id,),
        )
    response = client.post(f"/api/games/{game_id}/replay/verify", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "mismatched"
    assert payload["first_mismatch"]["differences"] == [
        {"path": "private_state", "redacted": True}
    ]
    assert "fang_sheng:player:trust" not in response.text
    assert '"expected":2' not in response.text


def test_timeline_and_prefix_api_are_public_and_validate_target(tmp_path):
    """时间线保留公开历史，前缀校验不读取后续当前投影，未知行动返回 404。"""
    client = TestClient(create_app(tmp_path / "api.db", model=SimulatedModel()))
    service = client.app.state.service
    game_id = client.post("/api/games", json={"protagonist": "江逢"}).json()["id"]
    start_social_chain(service, game_id)
    actions = action_rows(service.db, game_id)
    timeline = client.get(f"/api/games/{game_id}/timeline")
    assert timeline.status_code == 200
    data = timeline.json()
    assert data["baseline"]["available"] is True
    assert "snapshot_json" not in data["baseline"]
    assert [item["kind"] for item in data["items"]] == ["game_started", "action", "action"]
    assert data["items"][1]["narrative"]
    assert data["items"][2]["events"]
    assert "audit_json" not in timeline.text
    assert "fang_sheng:player:trust" not in timeline.text
    assert "方笙记得" not in timeline.text

    with service.db.transaction() as conn:
        conn.execute("UPDATE case_states SET clock=3 WHERE game_id=?", (game_id,))
    prefix = client.post(
        f"/api/games/{game_id}/replay/verify",
        json={"through_action_id": actions[0]["id"]},
    )
    assert prefix.status_code == 200
    assert prefix.json()["status"] == "matched"
    assert prefix.json()["checked_actions"] == 1
    assert client.post(
        f"/api/games/{game_id}/replay/verify", json={"through_action_id": "missing"}
    ).status_code == 404
    assert client.get("/api/games/missing/timeline").status_code == 404


@pytest.mark.parametrize("mutation,code", [
    ("DELETE FROM replay_baselines WHERE game_id=?", "baseline_missing"),
    ("UPDATE replay_baselines SET snapshot_hash='bad' WHERE game_id=?", "baseline_hash_mismatch"),
    ("UPDATE replay_baselines SET rules_version='old' WHERE game_id=?", "unsupported_version"),
    ("UPDATE replay_baselines SET snapshot_format=2 WHERE game_id=?", "unsupported_snapshot"),
    ("UPDATE actions SET command_json=NULL WHERE game_id=?", "invalid_action_record"),
])
def test_unavailable_reasons_are_explicit(tmp_path, mutation, code):
    """缺基线、哈希错误、版本和命令记录问题均不得伪装成一致。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    act(service, game_id, "接受方笙的委托", "accept")
    with db.transaction() as conn:
        conn.execute(mutation, (game_id,))
    result = ReplayEngine(db).verify(game_id)
    assert result["status"] == "unavailable"
    assert result["reason"]["code"] == code


def test_invalid_roll_external_mutation_and_budgets_are_unavailable(tmp_path):
    """非法骰点、非行动机械变化及两种预算耗尽必须安全停止。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    act(service, game_id, "接受方笙的委托", "accept")
    act(service, game_id, "前往新栖公寓", "travel")
    act(service, game_id, "查看方笙住处", "inspect")
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT roll_json FROM actions WHERE game_id=? AND roll_json IS NOT NULL",
            (game_id,),
        ).fetchone()
        roll = json.loads(row["roll_json"])
        roll["modifier"] += 1
        conn.execute(
            "UPDATE actions SET roll_json=? WHERE game_id=? AND roll_json IS NOT NULL",
            (json.dumps(roll), game_id),
        )
    result = ReplayEngine(db).verify(game_id)
    assert result["reason"]["code"] == "invalid_action_record"

    with db.transaction() as conn:
        row = conn.execute(
            "SELECT roll_json FROM actions WHERE game_id=? AND roll_json IS NOT NULL",
            (game_id,),
        ).fetchone()
        roll = json.loads(row["roll_json"])
        roll["modifier"] -= 1
        conn.execute(
            "UPDATE actions SET roll_json=? WHERE game_id=? AND roll_json IS NOT NULL",
            (json.dumps(roll), game_id),
        )
    assert ReplayEngine(db, max_actions=2).verify(game_id)["reason"]["code"] == (
        "replay_budget_exceeded"
    )
    ticks = iter([0.0, 1.0])
    timed = ReplayEngine(db, timeout_seconds=0.5, clock=lambda: next(ticks)).verify(game_id)
    assert timed["reason"]["code"] == "replay_budget_exceeded"
    assert timed["checked_actions"] == 0

    db.invalidate_fact(game_id, "fangsheng_present", "测试外部机械变化")
    assert ReplayEngine(db).verify(game_id)["reason"]["code"] == (
        "unsupported_external_mutation"
    )


def test_comparison_ignores_physical_ids_but_keeps_duplicate_semantic_records():
    """规范化比较不看物理编号，同时不能吞掉重复知识或履历。"""
    expected = {
        "knowledge": [{"content": "同一证词", "source": "1:action_committed"}],
        "character_history": [],
    }
    actual = {
        "knowledge": [{"content": "同一证词", "source": "1:action_committed"}],
        "character_history": [],
    }
    assert compare_snapshots(expected, actual) == []
    actual["knowledge"].append(dict(actual["knowledge"][0]))
    assert compare_snapshots(expected, actual)[0]["path"] == "knowledge[1]"
