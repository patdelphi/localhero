"""程序说明：先行验证第六阶段认知来源、记忆衰减、追加纠正、迁移与回放。"""

import copy
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.action_protocol import RULES_VERSION, StateConflict
from app.case_content import CONTENT_VERSION
from app.cognition_engine import (
    build_cognition_view,
    effective_precision,
    validate_cognition_changes,
)
from app.main import create_app
from app.model import SimulatedModel
from app.npc_decision import decide_npc_plan
from app.replay_engine import ReplayEngine
from app.store import Database


def make_client(tmp_path):
    """建立只使用临时数据库的第六阶段客户端。"""
    client = TestClient(create_app(tmp_path / "phase6.db", model=SimulatedModel()))
    return client, client.app.state.service, client.app.state.service.db


def act(service, game_id, text, request_id, action_id=None):
    """以固定请求标识提交真实行动。"""
    return service.act(game_id, text, request_id, action_id=action_id)


def start_chain(service, game_id, ask_details=True):
    """建立委托、可选误判证词、安全承诺和到期计划。"""
    act(service, game_id, "接受方笙的委托", "accept")
    if ask_details:
        act(service, game_id, "询问委托细节", "details", "commission_details")
    act(service, game_id, "安抚方笙", "reassure", "reassure_fangsheng")
    act(service, game_id, "前往新栖公寓", "travel")
    return act(service, game_id, "查看方笙住处", "inspect")


def all_knowledge(db, game_id):
    """读取内部认知，仅供临时数据库测试核对来源图。"""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM knowledge_records WHERE game_id=? ORDER BY rowid", (game_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def raw_audit(db, game_id, request_id):
    """读取未裁剪审计，核对内部来源和衰减理由。"""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT audit_json FROM actions WHERE game_id=? AND request_id=?",
            (game_id, request_id),
        ).fetchone()
    return json.loads(row["audit_json"])


def find_record(records, text):
    """按固定公开或内部文本定位唯一认知。"""
    return next(item for item in records if text in item["content"])


def memory(record_id, holder="fang_sheng", precision="exact", observed_at=0):
    """构造纯函数测试所需的记忆记录。"""
    return {
        "id": record_id,
        "knowledge_id": record_id,
        "holder_id": holder,
        "kind": "memory",
        "fact_id": None,
        "content": f"记忆 {record_id}",
        "accuracy": "honest",
        "visibility": "private",
        "source_record_id": None,
        "observed_at": observed_at,
        "precision": precision,
        "corrects_record_id": None,
    }


def test_effective_precision_boundaries_are_pure_and_legacy_unknown_never_recovers():
    """0/3/4/6/7 点边界确定衰减，原记录不变且旧 unknown 不回升。"""
    record = memory("old")
    original = copy.deepcopy(record)
    assert [effective_precision(record, point) for point in (0, 3, 4, 6, 7, 9)] == [
        "exact", "exact", "vague", "vague", "fragmentary", "fragmentary",
    ]
    assert record == original
    vague = memory("vague", precision="vague")
    assert effective_precision(vague, 4) == "vague"
    assert effective_precision(vague, 7) == "fragmentary"
    legacy = memory("legacy", precision="unknown", observed_at=None)
    assert effective_precision(legacy, 99) == "unknown"
    testimony = memory("spoken", precision="vague", observed_at=None)
    testimony["kind"] = "testimony"
    assert effective_precision(testimony, 99) == "vague"
    with pytest.raises(ValueError, match="观察时间"):
        effective_precision(memory("future", observed_at=8), 7)
    with pytest.raises(ValueError, match="精度"):
        effective_precision(memory("bad", precision="certain"), 0)


def test_source_view_is_holder_scoped_and_correction_is_append_only():
    """来源图只含本人记录，纠正追加投影且不修改原记忆正文。"""
    observation = memory("obs")
    observation["kind"] = "observation"
    mistaken = memory("inference")
    mistaken["source_record_id"] = "obs"
    correction = memory("correction", observed_at=3)
    correction["source_record_id"] = "obs"
    correction["corrects_record_id"] = "inference"
    other = memory("other", holder="shao_qian")
    records = [observation, mistaken, correction, other]
    original = copy.deepcopy(records)
    view = build_cognition_view("fang_sheng", records, 3)
    assert [item["knowledge_id"] for item in view] == ["obs", "inference", "correction"]
    assert view[1]["corrected_by"] == ["correction"]
    assert view[1]["content"] == "记忆 inference"
    assert records == original

    invalid = copy.deepcopy(records)
    invalid[2]["holder_id"] = "shao_qian"
    with pytest.raises(ValueError, match="同一持有者"):
        build_cognition_view("shao_qian", invalid, 3)


def test_v6_new_game_has_declared_initial_cognition_without_new_case_facts(tmp_path):
    """新档具有两组来源完整的私密观察与记忆，但不会把误判提升为事实。"""
    _, service, db = make_client(tmp_path)
    game_id = service.create_game("江逢")["id"]
    records = all_knowledge(db, game_id)
    assert len(records) == 5
    assert all(item["holder_id"] == "fang_sheng" for item in records)
    assert all(item["visibility"] == "private" for item in records)
    assert all(item["observed_at"] == 0 and item["precision"] == "exact" for item in records)
    inference = find_record(records, "当晚只有邵谦使用凭证")
    assert inference["kind"] == "memory" and inference["fact_id"] is None
    assert inference["source_record_id"] is not None
    assert db.get_case_facts(game_id) == []
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(knowledge_records)")
        }
    assert {"source_record_id", "observed_at", "precision", "corrects_record_id"} <= columns
    assert RULES_VERSION == "action-pipeline-1.3"
    assert CONTENT_VERSION == "c01-1.3"


def test_commission_details_generates_honest_mistake_without_mechanical_grants(tmp_path):
    """委托细节追加来源明确的诚实误判，但不生成事实、线索或 Clock。"""
    _, service, db = make_client(tmp_path)
    game_id = service.create_game("江逢")["id"]
    act(service, game_id, "接受方笙的委托", "accept")
    before_clock = db.get_case_state(game_id)["clock"]
    act(service, game_id, "询问委托细节", "details", "commission_details")
    mistake = find_record(db.get_player_knowledge(game_id), "我怀疑当晚只有邵谦使用凭证")
    records = all_knowledge(db, game_id)
    internal_mistake = find_record(records, "我怀疑当晚只有邵谦使用凭证")
    source = next(
        item for item in records if item["id"] == internal_mistake["source_record_id"]
    )
    assert mistake["source_record_id"] is None
    assert internal_mistake["source_record_id"] == source["id"]
    assert mistake["accuracy"] == "honest" and mistake["precision"] == "exact"
    assert mistake["fact_id"] is None and source["kind"] == "memory"
    assert db.get_case_state(game_id)["clock"] == before_clock
    assert {item["fact_id"] for item in db.get_case_facts(game_id)} == {"commission"}
    assert raw_audit(db, game_id, "details")["audit_version"] == 3


def test_normal_chain_appends_private_and_public_corrections(tmp_path):
    """世界时间3正常分享排班，并追加内部与公开纠正，旧证词正文保持不变。"""
    _, service, db = make_client(tmp_path)
    game_id = service.create_game("江逢")["id"]
    start_chain(service, game_id)
    records = all_knowledge(db, game_id)
    old_mistake = find_record(records, "我怀疑当晚只有邵谦使用凭证")
    private_correction = find_record(records, "最后登录不足以证明当晚只有邵谦使用凭证")
    public_correction = next(
        item for item in records
        if item["kind"] == "testimony" and item["corrects_record_id"] == old_mistake["id"]
    )
    assert private_correction["visibility"] == "private"
    assert private_correction["corrects_record_id"] == find_record(records, "当晚只有邵谦使用凭证")["id"]
    assert public_correction["visibility"] == "player"
    assert "我怀疑当晚只有邵谦使用凭证" in old_mistake["content"]
    assert "撤回" not in old_mistake["content"]
    assert db.get_case_state(game_id)["world_time"] == 3
    assert {item["fact_id"] for item in db.get_case_facts(game_id)} == {
        "commission", "fangsheng_present",
    }
    audit = raw_audit(db, game_id, "inspect")
    assert audit["audit_version"] == 3
    assert audit["cognition"]["world_time"] == 3
    assert any(item["effective_precision"] == "exact" for item in audit["cognition"]["decay"])
    assert len(audit["cognition"]["records"]) >= 3


def test_correction_without_public_mistake_does_not_invent_player_history(tmp_path):
    """玩家未听过误判时只追加私密纠正，不伪造公开纠正目标。"""
    _, service, db = make_client(tmp_path)
    game_id = service.create_game("江逢")["id"]
    start_chain(service, game_id, ask_details=False)
    records = all_knowledge(db, game_id)
    assert any(item["corrects_record_id"] for item in records if item["visibility"] == "private")
    assert not any(item["corrects_record_id"] for item in records if item["visibility"] == "player")


def test_vague_and_fragmentary_memories_select_safe_fallbacks(tmp_path):
    """模糊记忆只给谨慎提醒，破碎记忆等待且计划不完成、不产生纠正。"""
    _, service, db = make_client(tmp_path)
    game_id = service.create_game("江逢")["id"]
    act(service, game_id, "接受方笙的委托", "accept")
    act(service, game_id, "安抚方笙", "reassure", "reassure_fangsheng")
    context = db.get_decision_context(game_id)
    plan = context["local_plans"][0]

    vague_context = copy.deepcopy(context)
    vague_context["after_time"] = 4
    vague = decide_npc_plan(plan, vague_context)
    assert vague["selected_candidate_id"] == "share_safe_reminder"
    assert not any(item["corrects_record_id"] for item in vague["changes"]["knowledge"])

    fragmentary_context = copy.deepcopy(context)
    fragmentary_context["after_time"] = 7
    fragmentary = decide_npc_plan(plan, fragmentary_context)
    assert fragmentary["selected_candidate_id"] == "wait"
    assert fragmentary["changes"]["plans"] == []
    assert fragmentary["changes"]["knowledge"] == []
    excluded = {
        item["candidate_id"]: item["excluded_reasons"] for item in fragmentary["candidates"]
    }
    assert "insufficient_precision" in excluded["share_schedule"]
    assert "insufficient_precision" in excluded["share_safe_reminder"]


def test_public_knowledge_and_audit_redact_private_source_graph(tmp_path):
    """公开接口只暴露公开纠正关系，不泄露私密记忆正文、ID 或来源链。"""
    client, service, db = make_client(tmp_path)
    game_id = service.create_game("江逢")["id"]
    start_chain(service, game_id)
    private = find_record(all_knowledge(db, game_id), "当晚只有邵谦使用凭证")

    knowledge_response = client.get(f"/api/games/{game_id}/knowledge")
    assert knowledge_response.status_code == 200
    assert private["id"] not in knowledge_response.text
    assert private["content"] not in knowledge_response.text
    public_items = knowledge_response.json()["items"]
    corrected = find_record(public_items, "我怀疑当晚只有邵谦使用凭证")
    correction = next(item for item in public_items if item.get("corrects_record_id") == corrected["knowledge_id"])
    assert corrected["has_correction"] is True
    assert correction["source_record_id"] is None

    audit_response = client.get(f"/api/games/{game_id}/audit?limit=20")
    assert audit_response.status_code == 200
    assert private["id"] not in audit_response.text
    assert private["content"] not in audit_response.text
    inspect_entry = next(item for item in audit_response.json()["items"] if item["request_id"] == "inspect")
    assert all(item["visibility"] == "player" for item in inspect_entry["audit"]["cognition"]["records"])


def test_invalid_source_rolls_back_player_action_and_all_cognition(tmp_path, monkeypatch):
    """跨持有者来源导致整个行动回滚，不留主行动、骰点、证词或计划变化。"""
    _, service, db = make_client(tmp_path)
    game_id = service.create_game("江逢")["id"]
    act(service, game_id, "接受方笙的委托", "accept")
    act(service, game_id, "安抚方笙", "reassure", "reassure_fangsheng")
    act(service, game_id, "前往新栖公寓", "travel")
    before_events = db.get_events(game_id)
    original = Database._apply_simulation_changes

    def invalid_source(conn, game_id_value, action_id, simulation, after_time):
        altered = copy.deepcopy(simulation)
        altered["knowledge"][0]["source_record_id"] = "not-a-real-source"
        return original(conn, game_id_value, action_id, altered, after_time)

    monkeypatch.setattr(Database, "_apply_simulation_changes", staticmethod(invalid_source))
    with pytest.raises(ValueError, match="来源"):
        act(service, game_id, "查看方笙住处", "inspect")
    assert db.get_case_state(game_id)["world_time"] == 2
    assert db.get_local_plans(game_id)[0]["status"] == "pending"
    assert db.get_events(game_id) == before_events


def test_v5_migration_preserves_legacy_unknown_and_does_not_backfill_initial_graph(tmp_path):
    """v5 备份迁移只补 unknown 四字段，不给旧档伪造新档初始认知。"""
    _, service, db = make_client(tmp_path)
    game_id = service.create_game("江逢")["id"]
    act(service, game_id, "接受方笙的委托", "accept")
    with db.connect() as conn:
        before_count = conn.execute(
            "SELECT COUNT(*) FROM knowledge_records WHERE game_id=?", (game_id,)
        ).fetchone()[0]
        old_texts = [row[0] for row in conn.execute(
            "SELECT content FROM knowledge_records WHERE game_id=?", (game_id,)
        )]
    with db.transaction() as conn:
        conn.execute("DROP INDEX idx_knowledge_source_record")
        conn.execute("DROP INDEX idx_knowledge_corrects_record")
        for column in ("source_record_id", "observed_at", "precision", "corrects_record_id"):
            conn.execute(f"ALTER TABLE knowledge_records DROP COLUMN {column}")
        conn.execute("PRAGMA user_version=5")

    Database(db.path).initialize()
    assert db.path.with_name(f"{db.path.name}.pre-v6.bak").exists()
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
        rows = conn.execute(
            "SELECT * FROM knowledge_records WHERE game_id=?", (game_id,)
        ).fetchall()
    assert len(rows) == before_count
    assert [row["content"] for row in rows] == old_texts
    assert all(row["precision"] == "unknown" for row in rows)
    assert all(row["source_record_id"] is None and row["observed_at"] is None for row in rows)


def test_replay_checks_precision_sources_corrections_and_redacts_private_tamper(tmp_path):
    """正常链可回放；公开纠正目标和私密精度篡改均能被识别且私密值不下发。"""
    _, service, db = make_client(tmp_path)
    game_id = service.create_game("江逢")["id"]
    start_chain(service, game_id)
    engine = ReplayEngine(db)
    assert engine.verify(game_id)["status"] == "matched"
    private = find_record(all_knowledge(db, game_id), "当晚只有邵谦使用凭证")
    with db.transaction() as conn:
        conn.execute(
            "UPDATE knowledge_records SET precision='fragmentary' WHERE id=?", (private["id"],)
        )
    private_result = engine.verify(game_id)
    assert private_result["status"] == "mismatched"
    assert private_result["first_mismatch"]["differences"] == [
        {"path": "private_state", "redacted": True}
    ]
    with db.transaction() as conn:
        conn.execute("UPDATE knowledge_records SET precision='exact' WHERE id=?", (private["id"],))
        conn.execute(
            "UPDATE knowledge_records SET corrects_record_id=NULL "
            "WHERE game_id=? AND kind='testimony' AND corrects_record_id IS NOT NULL",
            (game_id,),
        )
    public_result = engine.verify(game_id)
    assert public_result["status"] == "mismatched"
    assert any(
        "corrects_record_id" in item["path"]
        for item in public_result["first_mismatch"]["differences"]
    )
