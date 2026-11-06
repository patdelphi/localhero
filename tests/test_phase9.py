"""程序说明：先行验证第九阶段受限情节导演的白名单、冷却、关闭、审计与回放。"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.director import (
    DEFAULT_INTERVAL,
    DIRECTOR_EFFECTS,
    DIRECTOR_VERSION,
    evaluate_director,
)
from app.game import GameService
from app.llm_model import ProviderModel
from app.main import create_app
from app.model import SimulatedModel
from app.provider_config import load_provider_config
from app.store import Database


def make_service(tmp_path, model=None, enabled=False, interval=DEFAULT_INTERVAL):
    """创建只使用临时数据库的情节导演服务。"""
    db = Database(tmp_path / "phase9.db").initialize()
    return GameService(
        db,
        model or SimulatedModel(),
        director_enabled=enabled,
        director_interval=interval,
    ), db


class ProposalModel(SimulatedModel):
    """按顺序返回预设提案，其余能力沿用确定性模拟模型。"""

    def __init__(self, proposals):
        super().__init__()
        self.proposals = list(proposals)

    def propose_director(self, context):
        """返回下一条预设提案，并标注来源；用尽后返回 None。"""
        if not self.proposals:
            return None
        proposal = dict(self.proposals.pop(0))
        proposal.setdefault("source", "simulated")
        return proposal


def provider_env(**overrides):
    """生成最小可用的 Provider 环境，密钥固定为测试值。"""
    values = {
        "AI_CURRENT_PROVIDER": "1",
        "AI_CURRENT_MODEL": "1.1",
        "AI_PROVIDER_1_NAME": "dashscope",
        "AI_PROVIDER_1_BASE_URL": "https://example.test/v1",
        "AI_PROVIDER_1_API_KEY": "test-secret-key",
        "AI_PROVIDER_1_TIMEOUT_SECONDS": "30",
        "AI_PROVIDER_1_MAX_RETRIES": "1",
        "AI_PROVIDER_1_MAX_OUTPUT_TOKENS": "8192",
        "AI_MODEL_1_1_NAME": "qwen-test",
    }
    values.update(overrides)
    return values


def completion(content):
    """构造 OpenAI 兼容响应。"""
    return httpx.Response(
        200,
        json={
            "model": "qwen-test",
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 8},
        },
    )


def director_model_with(handler):
    """建立只走模拟传输的在线模型。"""
    config = load_provider_config(environ=provider_env())
    return ProviderModel(
        config,
        fallback=SimulatedModel(),
        transport=httpx.MockTransport(handler),
        sleep=lambda _seconds: None,
    )


def action_events(count, beat=False):
    """构造只含行动与可选已接受节拍的事件序列。"""
    events = [
        {"kind": "action_committed", "payload": {"input": f"行动{index}"}}
        for index in range(count)
    ]
    if beat:
        events.append({"kind": "director_beat", "payload": {"beat_type": "environment_complication"}})
        events.append({"kind": "action_committed", "payload": {"input": "后续行动"}})
    return events


def test_valid_proposal_is_accepted_with_whitelisted_text():
    """合法提案被接受，展示文本必须来自白名单且没有机械变化。"""
    intent = {"kind": "inspect"}
    section = evaluate_director(
        action_events(DEFAULT_INTERVAL),
        ProposalModel([{
            "beat_type": "environment_complication",
            "effect_id": "env.rain_gutter",
            "target_action": "inspect",
            "reason": "雨声变重",
        }]),
        intent,
        "OC-01",
        interval=DEFAULT_INTERVAL,
        enabled=True,
    )

    assert section["version"] == DIRECTOR_VERSION
    assert section["accepted"] is True
    assert section["validation"]["rule_id"] == "director.accepted"
    assert section["proposal"]["source"] == "simulated"
    assert section["effect"]["text"] == DIRECTOR_EFFECTS["env.rain_gutter"]["text"]
    assert section["effect"]["clock_delta"] == 0
    assert section["effect"]["fact_changes"] == 0
    assert section["proposal"]["proposal_id"]


def test_trigger_cooldown_blocks_early_proposal():
    """行动不足间隔时不询问模型，也不产生提案。"""
    section = evaluate_director(
        action_events(1),
        ProposalModel([]),
        {"kind": "inspect"},
        "OC-01",
        interval=3,
        enabled=True,
    )

    assert section["trigger"]["checked"] is False
    assert section["trigger"]["rule_id"] == "director.trigger_cooldown"
    assert section["proposal"] is None
    assert section["accepted"] is False


@pytest.mark.parametrize(
    ("proposal", "rule_id"),
    [
        ({"beat_type": "new_character", "effect_id": "env.rain_gutter",
          "target_action": "inspect", "reason": "新增人物"}, "director.beat_type_not_allowed"),
        ({"beat_type": "environment_complication", "effect_id": "env.new_clue",
          "target_action": "inspect", "reason": "新增线索"}, "director.effect_not_allowed"),
        ({"beat_type": "environment_complication", "effect_id": "env.rain_gutter",
          "target_action": "accept_commission", "reason": "目标不符"}, "director.target_mismatch"),
        ({"beat_type": "environment_complication", "effect_id": "env.rain_gutter",
          "target_action": "inspect", "reason": "出现新的线索，共3条"}, "director.reason_rejected"),
        ({"beat_type": "environment_complication", "effect_id": "env.rain_gutter",
          "target_action": "inspect", "reason": "苗雨出现在门口"}, "director.reason_rejected"),
    ],
)
def test_invalid_proposals_are_rejected(proposal, rule_id):
    """越权提案全部拒绝，并给出稳定规则编号。"""
    section = evaluate_director(
        action_events(DEFAULT_INTERVAL),
        ProposalModel([proposal]),
        {"kind": "inspect"},
        "OC-01",
        interval=DEFAULT_INTERVAL,
        enabled=True,
    )

    assert section["accepted"] is False
    assert section["validation"]["rule_id"] == rule_id
    assert section["effect"] is None


def test_duplicate_beat_is_rejected():
    """同档已接受同一节拍时不再接受第二次。"""
    section = evaluate_director(
        action_events(DEFAULT_INTERVAL, beat=True),
        ProposalModel([{
            "beat_type": "environment_complication",
            "effect_id": "env.light_flicker",
            "target_action": "inspect",
            "reason": "灯光变化",
        }]),
        {"kind": "inspect"},
        "OC-01",
        interval=DEFAULT_INTERVAL,
        enabled=True,
    )

    assert section["accepted"] is False
    assert section["validation"]["rule_id"] == "director.no_repeat_beat"


def test_missing_proposal_is_rejected_without_error():
    """模型不返回提案时记录拒绝原因，不影响行动本身。"""
    section = evaluate_director(
        action_events(DEFAULT_INTERVAL),
        ProposalModel([]),
        {"kind": "inspect"},
        "OC-01",
        interval=DEFAULT_INTERVAL,
        enabled=True,
    )

    assert section["accepted"] is False
    assert section["validation"]["rule_id"] == "director.proposal_unavailable"


def test_disabled_director_matches_phase8_audit(tmp_path):
    """关闭时审计仍为 v3，事件流中没有情节节拍。"""
    service, db = make_service(tmp_path, enabled=False, interval=2)
    game_id = service.create_game("江逢")["id"]
    for index, text in enumerate(["接受方笙的委托", "和唐葵谈谈", "查看现场"]):
        service.act(game_id, text, f"request-{index}")

    action = db.get_action_by_request(game_id, "request-2")
    assert action["audit"]["audit_version"] == 3
    assert "director" not in action["audit"]
    assert not any(event["kind"] == "director_beat" for event in db.get_events(game_id))


def test_accepted_beat_is_committed_in_single_event(tmp_path):
    """接受提案后审计为 v4，并只写一条情节节拍事件。"""
    service, db = make_service(tmp_path, enabled=True, interval=2)
    game_id = service.create_game("江逢")["id"]
    for index, text in enumerate(["接受方笙的委托", "和唐葵谈谈", "查看现场"]):
        service.act(game_id, text, f"request-{index}")

    action = db.get_action_by_request(game_id, "request-2")
    audit = action["audit"]
    assert audit["audit_version"] == 4
    assert audit["director"]["accepted"] is True
    assert audit["director"]["proposal"]["source"] == "simulated"
    assert audit["director"]["effect"]["text"] in {
        item["text"] for item in DIRECTOR_EFFECTS.values()
    }

    beats = [event for event in db.get_events(game_id) if event["kind"] == "director_beat"]
    assert len(beats) == 1
    assert beats[0]["payload"]["text"] == audit["director"]["effect"]["text"]
    assert beats[0]["action_id"] == action["id"]


def test_rejected_proposal_has_no_partial_write(tmp_path):
    """被拒绝的提案不写事件、不改状态版本，行动仍正常完成。"""
    model = ProposalModel([{
        "beat_type": "environment_complication",
        "effect_id": "env.rain_gutter",
        "target_action": "accept_commission",
        "reason": "目标不符",
    }])
    service, db = make_service(tmp_path, model=model, enabled=True, interval=2)
    game_id = service.create_game("江逢")["id"]
    for index, text in enumerate(["接受方笙的委托", "和唐葵谈谈", "查看现场"]):
        service.act(game_id, text, f"request-{index}")

    action = db.get_action_by_request(game_id, "request-2")
    assert action["status"] == "complete"
    assert action["audit"]["audit_version"] == 4
    assert action["audit"]["director"]["accepted"] is False
    assert action["audit"]["director"]["effect"] is None
    assert not any(event["kind"] == "director_beat" for event in db.get_events(game_id))
    state = db.get_case_state(game_id)
    # 只有接受委托推进案件版本；拒绝提案与场景行动都没有额外写入。
    assert state["revision"] == 1


def test_replay_matches_with_accepted_beat(tmp_path):
    """已接受情节节拍的存档可以确定性回放。"""
    service, _ = make_service(tmp_path, enabled=True, interval=2)
    game_id = service.create_game("江逢")["id"]
    for index, text in enumerate(["接受方笙的委托", "和唐葵谈谈", "查看现场"]):
        service.act(game_id, text, f"request-{index}")

    result = service.verify_replay(game_id)
    assert result["status"] == "matched"
    assert result["checked_actions"] == 3


def test_provider_director_parses_whitelist_json():
    """在线模型只提交白名单编号，非法编号不产生提案。"""
    captured = {}

    def handler(request):
        body = json.loads(request.content)
        system = body["messages"][0]["content"]
        if "情节导演" in system:
            captured["director"] = body
            return completion(json.dumps({
                "beat_type": "environment_complication",
                "effect_id": "env.door_rattle",
                "target_action": "inspect",
                "reason": "门外有响动",
            }, ensure_ascii=False))
        return completion("你查看四周，环境保持原样。")

    model = director_model_with(handler)
    proposal = model.propose_director({
        "当前行动编号": "inspect",
        "当前地点": "OC-01",
        "可选效果": [
            {"effect_id": effect_id, "text": item["text"]}
            for effect_id, item in DIRECTOR_EFFECTS.items()
        ],
    })

    assert proposal["effect_id"] == "env.door_rattle"
    assert proposal["target_action"] == "inspect"
    assert proposal["source"] == "provider"
    serialized = json.dumps(captured["director"], ensure_ascii=False)
    assert "env.new_clue" not in serialized

    def invalid_handler(request):
        body = json.loads(request.content)
        if "情节导演" in body["messages"][0]["content"]:
            return completion('{"beat_type":"environment_complication","effect_id":"env.new_clue"}')
        return completion("环境保持原样。")

    assert director_model_with(invalid_handler).propose_director({
        "当前行动编号": "inspect",
        "当前地点": "OC-01",
        "可选效果": [{"effect_id": "env.rain_gutter"}],
    }) is None


def test_api_director_toggle(tmp_path):
    """界面开关可在会话内切换，且不写入存档。"""
    app = create_app(tmp_path / "api.db", model=SimulatedModel(), director_enabled=False)
    client = TestClient(app)
    game_id = client.post("/api/games", json={"protagonist": "江逢"}).json()["id"]

    state = client.get(f"/api/games/{game_id}/director").json()
    assert state["enabled"] is False
    assert state["interval"] == DEFAULT_INTERVAL
    assert state["beat_types"] == ["environment_complication"]

    toggled = client.post(f"/api/games/{game_id}/director", json={"enabled": True})
    assert toggled.status_code == 200
    assert toggled.json()["enabled"] is True

    events = client.get(f"/api/games/{game_id}").json()["events"]
    assert len(events) == 1


def test_audit_exposes_proposer_and_acceptance_reason(tmp_path):
    """审计可回答“谁提出、为何接受”。"""
    service, db = make_service(tmp_path, enabled=True, interval=2)
    game_id = service.create_game("江逢")["id"]
    for index, text in enumerate(["接受方笙的委托", "和唐葵谈谈", "查看现场"]):
        service.act(game_id, text, f"request-{index}")

    items = service.get_audit(game_id)["items"]
    director = next(
        item["audit"]["director"] for item in items
        if item["audit"].get("director", {}).get("accepted")
    )
    assert director["proposal"]["proposal_id"]
    assert director["proposal"]["source"] in {"provider", "simulated"}
    assert director["proposal"]["reason"]
    assert director["validation"]["rule_id"] == "director.accepted"
