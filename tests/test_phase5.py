"""程序说明：先行验证第五阶段回应者、NPC自主决策、场景导演、审计与回放。"""

import copy
import json

import pytest
from fastapi.testclient import TestClient

from app.action_pipeline import build_structured_changes
from app.action_protocol import StateConflict
from app.case_content import AUTONOMY_PLAN_DEFINITIONS, CONTENT_VERSION
from app.case_engine import action_by_id
from app.game import GameService
from app.main import create_app
from app.model import SimulatedModel
from app.npc_decision import build_npc_knowledge, decide_npc_plan
from app.replay_engine import ReplayEngine
from app.scene_director import select_scene
from app.social_engine import build_social_changes, judge_social_response
from app.store import Database


def make_service(tmp_path, model=None):
    """建立只使用临时数据库的第五阶段服务。"""
    db = Database(tmp_path / "phase5.db").initialize()
    return GameService(db, model or SimulatedModel()), db


def act(service, game_id, text, request_id, action_id=None):
    """以固定请求标识提交真实行动。"""
    return service.act(game_id, text, request_id, action_id=action_id)


def start_social_chain(service, game_id):
    """建立委托、安全承诺、私密信任和到期前的固定计划。"""
    act(service, game_id, "接受方笙的委托", "accept")
    act(service, game_id, "安抚方笙", "reassure", "reassure_fangsheng")


def reach_due_plan(service, game_id):
    """推进到世界时间3，使方笙补充计划到期。"""
    start_social_chain(service, game_id)
    act(service, game_id, "前往新栖公寓", "travel")
    return act(service, game_id, "查看方笙住处", "inspect")


def action_rows(db, game_id):
    """按提交顺序读取行动，供前缀回放使用。"""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM actions WHERE game_id=? ORDER BY rowid", (game_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def raw_audit(db, game_id, request_id):
    """读取数据库内部完整审计，验证玩家裁剪前的诊断信息。"""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT audit_json FROM actions WHERE game_id=? AND request_id=?",
            (game_id, request_id),
        ).fetchone()
    return json.loads(row["audit_json"])


def decision_context():
    """构造满足完整分享条件的纯函数输入，不依赖数据库。"""
    return {
        "after_time": 3,
        "social_states": [
            {
                "state_id": "fang_sheng:player:relationship",
                "holder_id": "fang_sheng", "target_id": "player",
                "kind": "relationship", "value_int": None, "value_text": "委托人",
                "visibility": "public", "status": "active",
            },
            {
                "state_id": "fang_sheng:player:trust",
                "holder_id": "fang_sheng", "target_id": "player",
                "kind": "trust", "value_int": 1, "value_text": None,
                "visibility": "private", "status": "active",
            },
        ],
        "local_plans": [{
            "plan_id": "fangsheng_followup", "holder_id": "fang_sheng",
            "scope": "c01", "due_time": 3, "status": "pending",
        }],
        "knowledge": [],
        "character_history": [{
            "holder_id": "fang_sheng", "kind": "social_memory",
            "content": "方笙记得：你承诺优先确认苗雨安全。",
            "structured": {"promise": "优先确认苗雨安全"}, "visibility": "private",
        }],
        "public_facts": [{"fact_id": "commission"}],
        "activated_scenes": [],
        "channels": ["remote_message"],
        "rules_version": "action-pipeline-1.2",
        "content_version": "c01-1.2",
    }


def test_response_judgment_gates_social_effects():
    """接受、拒绝、条件和回避回应必须明确控制社会效果权限。"""
    action = action_by_id("reassure_fangsheng")
    context = decision_context()
    states = context["social_states"]
    plans = context["local_plans"]

    accepted = judge_social_response(action, "no_roll", states[:1], [])
    assert accepted["response_kind"] == "accept"
    assert accepted["allow_social_effects"] is True
    refused = judge_social_response(action, "no_roll", [], [])
    assert refused["response_kind"] == "refuse"
    assert refused["allow_social_effects"] is False
    conditional = judge_social_response(action, "no_roll", states, plans)
    assert conditional["response_kind"] == "conditional"
    assert conditional["allow_social_effects"] is False
    evaded = judge_social_response(action, "success", states, [])
    assert evaded["response_kind"] == "evade"
    assert evaded["allow_social_effects"] is False

    empty = build_social_changes(action, "no_roll", 1, states, [], refused)
    assert empty == {"states": [], "history": [], "plans": [], "public": []}


def test_npc_knowledge_isolated_from_other_holders_and_unrelated_secrets():
    """其他人物私密知识和玩家秘密不得混入方笙视图或改变评分。"""
    context = decision_context()
    baseline = decide_npc_plan(context["local_plans"][0], context)
    knowledge = build_npc_knowledge("fang_sheng", [
        {"holder_id": "shao_qian", "fact_id": "company_secret"},
        {"holder_id": "player", "fact_id": "player_private_hypothesis"},
    ])
    assert "fang_sheng:old_shift_schedule" in knowledge
    assert "company_secret" not in knowledge
    assert "player_private_hypothesis" not in knowledge

    enriched = copy.deepcopy(context)
    enriched["knowledge"].extend([
        {
            "holder_id": "shao_qian", "kind": "secret", "fact_id": "company_secret",
            "content": "其他人物秘密", "accuracy": "direct", "visibility": "private",
        },
        {
            "holder_id": "player", "kind": "secret", "fact_id": "miaoyu_true_location",
            "content": "玩家私密假设", "accuracy": "direct", "visibility": "private",
        },
    ])
    assert decide_npc_plan(context["local_plans"][0], enriched) == baseline


def test_candidate_scoring_tiebreak_and_safe_trial_do_not_mutate_input():
    """候选评分、同分编号决胜和试算必须确定，且原上下文完全不变。"""
    context = decision_context()
    original = copy.deepcopy(context)
    decision = decide_npc_plan(context["local_plans"][0], context)
    assert context == original
    assert decision["selected_candidate_id"] == "share_schedule"
    assert [item["candidate_id"] for item in decision["candidates"]] == [
        "share_schedule", "share_safe_reminder", "wait",
    ]
    schedule = decision["candidates"][0]
    assert schedule["eligible"] is True
    assert schedule["score"]["total"] == sum(
        value for key, value in schedule["score"].items() if key != "total"
    )
    assert decide_npc_plan(context["local_plans"][0], context) == decision

    tied_definitions = copy.deepcopy(AUTONOMY_PLAN_DEFINITIONS)
    for candidate in tied_definitions["fangsheng_followup"]["candidates"]:
        candidate["score"] = {"goal": 0, "knowledge": 0, "risk": 0}
        candidate.pop("min_trust", None)
        candidate.pop("requires_memory", None)
    tied = decide_npc_plan(
        context["local_plans"][0], context, plan_definitions=tied_definitions
    )
    assert tied["selected_candidate_id"] == "share_safe_reminder"


def test_unknown_effect_is_excluded_and_wait_has_no_world_changes():
    """未声明效果不能借高分进入提交，等待候选也不完成计划。"""
    context = decision_context()
    definitions = copy.deepcopy(AUTONOMY_PLAN_DEFINITIONS)
    definitions["fangsheng_followup"]["candidates"][0]["effect_id"] = "arbitrary_power"
    decision = decide_npc_plan(
        context["local_plans"][0], context, plan_definitions=definitions
    )
    schedule = next(
        item for item in decision["candidates"] if item["candidate_id"] == "share_schedule"
    )
    assert schedule["eligible"] is False
    assert "unknown_effect" in schedule["excluded_reasons"]
    assert decision["selected_candidate_id"] == "share_safe_reminder"

    wait_context = copy.deepcopy(context)
    wait_context["knowledge"] = []
    wait_definitions = copy.deepcopy(AUTONOMY_PLAN_DEFINITIONS)
    wait_definitions["fangsheng_followup"]["candidates"] = [
        item for item in wait_definitions["fangsheng_followup"]["candidates"]
        if item["candidate_id"] == "wait"
    ]
    waited = decide_npc_plan(
        context["local_plans"][0], wait_context, plan_definitions=wait_definitions
    )
    assert waited["selected_candidate_id"] == "wait"
    assert waited["changes"] == {
        "plans": [], "states": [], "knowledge": [], "history": [], "public": [],
    }


def test_scene_director_filters_requirements_and_no_scene_discards_changes():
    """渠道、关系和重复激活不合法时，候选产物也必须安全丢弃。"""
    context = decision_context()
    decision = decide_npc_plan(context["local_plans"][0], context)
    selected = select_scene(decision, context)
    assert selected["scene"]["scene_id"] == "fangsheng_remote_schedule"
    assert selected["changes"]["plans"] == [{
        "plan_id": "fangsheng_followup", "status": "completed",
    }]

    for mutation in ("channel", "relationship", "repeat"):
        altered = copy.deepcopy(context)
        if mutation == "channel":
            altered["channels"] = []
        elif mutation == "relationship":
            altered["social_states"] = [altered["social_states"][1]]
        else:
            altered["activated_scenes"] = ["fangsheng_remote_schedule"]
        fallback = select_scene(decision, altered)
        assert fallback["scene"] is None
        assert fallback["changes"]["plans"] == []
        assert fallback["changes"]["knowledge"] == []
        assert all(not item["selected"] for item in fallback["scenes"])


def test_complete_chain_has_v3_audit_scene_and_unchanged_core_permissions(tmp_path):
    """正常方笙链仍分享原证词，新增场景轨迹但不新增核心事实权限。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    reach_due_plan(service, game_id)

    scene_events = [
        event for event in db.get_events(game_id) if event["kind"] == "scene_activated"
    ]
    assert len(scene_events) == 1
    assert scene_events[0]["payload"] == {
        "scene_id": "fangsheng_remote_schedule",
        "plan_id": "fangsheng_followup",
        "holder_id": "fang_sheng",
        "candidate_id": "share_schedule",
        "channel": "remote_message",
        "presentation_key": "fangsheng_remote_schedule",
        "rules_version": "action-pipeline-1.3",
        "content_version": "c01-1.3",
    }
    assert any(
        "共享账户备注" in item["content"] for item in db.get_player_knowledge(game_id)
    )
    assert {item["fact_id"] for item in db.get_case_facts(game_id)} == {
        "commission", "fangsheng_present",
    }
    audit = raw_audit(db, game_id, "inspect")
    assert audit["audit_version"] == 3
    assert audit["autonomy"]["decisions"][0]["selected_candidate_id"] == "share_schedule"
    assert audit["autonomy"]["decisions"][0]["candidates"][0]["score"]["total"] > 0
    assert audit["autonomy"]["random_sequence_after_player"] == (
        audit["autonomy"]["random_sequence_before"] + 1
    )


def test_public_audit_and_timeline_redact_internal_decision_data(tmp_path):
    """玩家只看最终选择，不能读取知识引用、评分、私密信任或排除理由。"""
    client = TestClient(create_app(tmp_path / "public.db", model=SimulatedModel()))
    service = client.app.state.service
    game_id = client.post("/api/games", json={"protagonist": "江逢"}).json()["id"]
    reach_due_plan(service, game_id)

    audit_response = client.get(f"/api/games/{game_id}/audit?limit=10")
    assert audit_response.status_code == 200
    inspect_entry = next(
        item for item in audit_response.json()["items"] if item["request_id"] == "inspect"
    )
    decision = inspect_entry["audit"]["autonomy"]["decisions"][0]
    assert decision["selected_candidate_id"] == "share_schedule"
    assert "knowledge_refs" not in decision
    assert "candidates" not in decision
    assert "knowledge_refs" not in audit_response.text
    assert '"score"' not in audit_response.text
    assert "excluded_reasons" not in json.dumps(decision, ensure_ascii=False)
    assert "fang_sheng:player:trust" not in audit_response.text

    timeline = client.get(f"/api/games/{game_id}/timeline")
    assert timeline.status_code == 200
    assert '"kind":"scene_activated"' in timeline.text
    assert "fangsheng_remote_schedule" in timeline.text
    assert '"score"' not in timeline.text
    assert "方笙记得" not in timeline.text


def test_decision_context_conflict_rolls_back_player_and_npc_changes(tmp_path, monkeypatch):
    """提交前社会上下文被外部修改时必须409，主行动和自主结果都不落库。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    start_social_chain(service, game_id)
    act(service, game_id, "前往新栖公寓", "travel")
    original_commit = db.commit_action

    def conflicting_commit(*args, **kwargs):
        with db.transaction() as conn:
            conn.execute(
                "UPDATE character_history SET content='外部新记忆' "
                "WHERE game_id=? AND kind='social_memory'", (game_id,)
            )
        return original_commit(*args, **kwargs)

    monkeypatch.setattr(db, "commit_action", conflicting_commit)
    with pytest.raises(StateConflict, match="决策上下文"):
        act(service, game_id, "查看方笙住处", "inspect")
    assert db.get_case_state(game_id)["world_time"] == 2
    assert db.get_local_plans(game_id)[0]["status"] == "pending"
    assert not any(event["kind"] == "scene_activated" for event in db.get_events(game_id))
    assert all(row["request_id"] != "inspect" for row in action_rows(db, game_id))


def test_idempotent_retry_preview_and_hypotheses_do_not_duplicate_autonomy(tmp_path):
    """请求重试和只读操作不得重复激活场景、推进计划或消耗随机序号。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    first = reach_due_plan(service, game_id)
    before_events = db.get_events(game_id)
    before_rolls = db.get_game(game_id)["roll_count"]

    second = act(service, game_id, "查看方笙住处", "inspect")
    assert second == first
    service.preview_action(game_id, "要求查看项目导出", "request_project_export")
    hypothesis = service.create_hypothesis(game_id, "不触发NPC")
    service.update_hypothesis(game_id, hypothesis["id"], "仍不触发NPC")
    service.delete_hypothesis(game_id, hypothesis["id"])
    assert db.get_events(game_id) == before_events
    assert db.get_game(game_id)["roll_count"] == before_rolls


def test_scene_write_failure_rolls_back_entire_action(tmp_path, monkeypatch):
    """场景事件失败时，行动、骰点、证词、计划和案件时间必须整体回滚。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    start_social_chain(service, game_id)
    act(service, game_id, "前往新栖公寓", "travel")
    before_rolls = db.get_game(game_id)["roll_count"]

    def fail_scene(*args, **kwargs):
        raise ValueError("测试场景写入失败")

    monkeypatch.setattr(Database, "_apply_scene_changes", staticmethod(fail_scene))
    with pytest.raises(ValueError, match="测试场景写入失败"):
        act(service, game_id, "查看方笙住处", "inspect")
    assert db.get_case_state(game_id)["world_time"] == 2
    assert db.get_game(game_id)["roll_count"] == before_rolls
    assert db.get_local_plans(game_id)[0]["status"] == "pending"
    assert all(row["request_id"] != "inspect" for row in action_rows(db, game_id))


def test_no_legal_scene_commits_only_player_action(tmp_path, monkeypatch):
    """导演无合法场景时玩家主行动可提交，但计划保持待处理且没有证词。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    start_social_chain(service, game_id)
    act(service, game_id, "前往新栖公寓", "travel")
    monkeypatch.setattr("app.scene_director.SCENE_DEFINITIONS", [])

    act(service, game_id, "查看方笙住处", "inspect")
    assert db.get_case_state(game_id)["world_time"] == 3
    assert db.get_local_plans(game_id)[0]["status"] == "pending"
    assert not any(
        "共享账户备注" in item["content"] for item in db.get_player_knowledge(game_id)
    )
    assert not any(event["kind"] == "scene_activated" for event in db.get_events(game_id))


def test_replay_checks_scene_identity_and_intermediate_prefix(tmp_path):
    """最新与中间前缀均可重算，篡改场景标识即使机械相同也不一致。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    reach_due_plan(service, game_id)
    actions = action_rows(db, game_id)
    engine = ReplayEngine(db)
    assert engine.verify(game_id)["status"] == "matched"
    prefix = engine.verify(game_id, actions[1]["id"])
    assert prefix["status"] == "matched"
    assert prefix["checked_actions"] == 2

    with db.transaction() as conn:
        row = conn.execute(
            "SELECT payload_json FROM events WHERE game_id=? AND kind='scene_activated'",
            (game_id,),
        ).fetchone()
        payload = json.loads(row["payload_json"])
        payload["scene_id"] = "tampered_scene"
        conn.execute(
            "UPDATE events SET payload_json=? WHERE game_id=? AND kind='scene_activated'",
            (json.dumps(payload, ensure_ascii=False), game_id),
        )
    result = engine.verify(game_id)
    assert result["status"] == "mismatched"
    assert any(
        item["path"].startswith("scenes")
        for item in result["first_mismatch"]["differences"]
    )


def test_old_action_pipeline_version_is_unavailable_but_history_readable(tmp_path):
    """1.1基线和行动不得按1.2规则伪装回放，公开历史仍保留。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    act(service, game_id, "接受方笙的委托", "accept")
    with db.transaction() as conn:
        conn.execute(
            "UPDATE replay_baselines SET rules_version='action-pipeline-1.1', "
            "content_version='c01-1.1' WHERE game_id=?", (game_id,)
        )
        conn.execute(
            "UPDATE actions SET rules_version='action-pipeline-1.1', "
            "content_version='c01-1.1' WHERE game_id=?", (game_id,)
        )
    result = ReplayEngine(db).verify(game_id)
    assert result["status"] == "unavailable"
    assert result["reason"]["code"] == "unsupported_version"
    timeline = ReplayEngine(db).timeline(game_id)
    assert len(timeline["items"]) == 2


def test_narrative_retry_does_not_repeat_response_decision_or_scene(tmp_path):
    """机械提交后的叙事失败只重试叙事，不增加场景和自主事件。"""
    service, db = make_service(tmp_path, SimulatedModel(fail_narrative_times=4))
    game_id = service.create_game("江逢")["id"]
    start_social_chain(service, game_id)
    act(service, game_id, "前往新栖公寓", "travel")
    pending = act(service, game_id, "查看方笙住处", "inspect")
    assert pending["status"] == "narrative_pending"
    before = db.get_events(game_id)
    service.retry_narrative(game_id, pending["action_id"])
    after = db.get_events(game_id)
    assert [event["kind"] for event in after].count("scene_activated") == 1
    assert len(after) == len(before) + 1
    assert after[-1]["kind"] == "narrative_completed"


def test_autonomy_processing_limits_fail_before_any_write(tmp_path):
    """到期计划超过有界上限时必须明确报错，不能静默截断或写入。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    case = db.get_case_state(game_id)
    context = db.get_decision_context(game_id)
    context["local_plans"] = [
        {
            "plan_id": f"plan-{index}", "holder_id": "fang_sheng",
            "scope": "c01", "due_time": 0, "status": "pending",
        }
        for index in range(9)
    ]
    with pytest.raises(ValueError, match="到期计划"):
        build_structured_changes(
            action_by_id("accept_commission"), case, "no_roll",
            decision_context=context,
        )
    assert len(action_rows(db, game_id)) == 0
    assert db.get_case_state(game_id)["revision"] == 0
    assert CONTENT_VERSION == "c01-1.3"
