"""程序说明：先行验证第八阶段叙事上下文白名单、裁剪、口吻与重复检测回退。"""

import json

import httpx
from app.game import GameService
from app.llm_model import ProviderModel
from app.model import SimulatedModel
from app.narrative_context import (
    MAX_CONTEXT_CHARS,
    REPEAT_SIMILARITY_THRESHOLD,
    build_narrative_context,
    context_size,
    ngram_similarity,
    trim_context,
)
from app.provider_config import load_provider_config
from app.store import Database


SECRET_TRUTH = "邵谦是主谋，内部评分99"


def make_service(tmp_path, model=None):
    """创建使用临时数据库和模拟模型的服务。"""
    db = Database(tmp_path / "phase8.db").initialize()
    return GameService(db, model or SimulatedModel()), db


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


def model_with(handler):
    """建立只走模拟传输的在线模型。"""
    config = load_provider_config(environ=provider_env())
    return ProviderModel(
        config,
        fallback=SimulatedModel(),
        transport=httpx.MockTransport(handler),
        sleep=lambda _seconds: None,
    )


def test_context_uses_committed_public_facts_only(tmp_path):
    """上下文只含公开白名单字段，当前行动不进入最近行动。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    steps = ["接受方笙的委托", "询问委托细节", "前往新栖公寓", "查看方笙住处"]
    for index, text in enumerate(steps):
        service.act(game_id, text, f"request-{index}")

    action = db.get_action_by_request(game_id, "request-3")
    events = db.get_events(game_id)
    knowledge = db.get_player_knowledge(game_id)
    # 私密认知即使被误传，也不得进入上下文。
    knowledge.append({"content": SECRET_TRUTH, "visibility": "private"})

    context = build_narrative_context(
        events, db.get_case_state(game_id), knowledge, action
    )

    assert context["当前地点"].startswith("新栖公寓")
    assert context["在场人物"] == ["方笙"]
    assert [item["行动"] for item in context["最近行动"]] == [
        "接受方笙的委托",
        "询问委托细节",
        "前往新栖公寓",
    ]
    assert context["上一条叙事结尾"]
    assert "方笙委托：寻找失踪的苗雨" in context["玩家已知线索"]
    assert context["口吻参考"][0]["人物"] == "方笙"
    dumped = json.dumps(context, ensure_ascii=False)
    assert SECRET_TRUTH not in dumped
    assert "评分" not in dumped


def test_recent_actions_are_limited_to_three_and_exclude_current(tmp_path):
    """最近行动最多三条，并且不包含当前正在叙事的行动。"""
    service, db = make_service(tmp_path)
    game_id = service.create_game("江逢")["id"]
    service.act(game_id, "接受方笙的委托", "request-0")
    for index in range(1, 5):
        service.act(game_id, "和唐葵谈谈", f"request-{index}")

    action = db.get_action_by_request(game_id, "request-4")
    context = build_narrative_context(
        db.get_events(game_id),
        db.get_case_state(game_id),
        db.get_player_knowledge(game_id),
        action,
    )

    labels = [item["行动"] for item in context["最近行动"]]
    assert len(labels) == 3
    assert "接受方笙的委托" not in labels
    assert labels == ["与唐葵交谈"] * 3


def test_context_trims_low_priority_fields_first():
    """超长上下文优先保留地点与最近行动，并记录被裁剪字段。"""
    context = {
        "当前地点": "新栖公寓（蜂巢区）",
        "在场人物": ["方笙"],
        "最近行动": [{"行动": "查看方笙住处", "判定": "成功"}],
        "玩家已知线索": ["线索" * 40 for _ in range(8)],
        "上一条叙事结尾": "尾" * 500,
        "口吻参考": [{"人物": "方笙", "口吻": "长" * 200}],
    }
    result = trim_context(context, max_chars=300)

    assert result["trimmed"] is True
    assert result["size"] <= 300
    assert result["context"]["当前地点"] == "新栖公寓（蜂巢区）"
    assert result["context"]["最近行动"] == context["最近行动"]
    # 较低优先级字段先被移除；线索可以保留一部分，只要总长度合规。
    assert "上一条叙事结尾" not in result["context"]
    assert "口吻参考" not in result["context"]
    assert len(result["context"].get("玩家已知线索", [])) < 8
    assert "上一条叙事结尾" in result["dropped"]
    assert "口吻参考" in result["dropped"]


def test_default_context_limit_is_bounded():
    """默认上限保持常量，供接入层复用。"""
    assert MAX_CONTEXT_CHARS == 1200


def test_ngram_similarity_detects_repetition():
    """相同文本相似度为1，不同文本低于阈值。"""
    same = "你俯身翻检桌面，指尖触到一层薄灰。抽屉滑轨松脱，开合时发出短促的摩擦声。"
    other = "窗外的雨停了，楼下传来送货车的刹车声。"

    assert ngram_similarity(same, same) == 1.0
    assert ngram_similarity(same, other) < REPEAT_SIMILARITY_THRESHOLD


def test_provider_prompt_contains_context_without_private_facts():
    """叙事提示包含白名单上下文，但私有真相不得进入请求体。"""
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return completion("你站在公寓走廊，雨声被门板隔在外面。")

    context = {
        "当前地点": "新栖公寓（蜂巢区）",
        "在场人物": ["方笙"],
        "口吻参考": [{"人物": "方笙", "口吻": "短句、谨慎"}],
        "最近行动": [{"行动": "查看方笙住处", "判定": "有代价成功"}],
        "上一条叙事结尾": "电梯面板还亮着。",
        "玩家已知线索": ["方笙委托：寻找失踪的苗雨"],
    }
    text = model_with(handler).narrate(
        {"kind": "case_action", "action_id": "inspect_fangsheng_room", "label": "查看方笙住处"},
        {"outcome": "partial", "total": 7},
        context=context,
        previous_narratives=[],
    )

    assert "公寓走廊" in text
    messages = captured["body"]["messages"]
    system = messages[0]["content"]
    fact = json.loads(messages[1]["content"])
    assert "叙事上下文" in system
    assert fact["叙事上下文"] == context
    serialized = json.dumps(captured["body"], ensure_ascii=False)
    assert SECRET_TRUTH not in serialized


def test_repetition_retries_once_then_falls_back_to_reference():
    """两次都高度雷同时，回退固定要点而不是继续接受重复文本。"""
    repeated = "你俯身翻检桌面，指尖触到一层薄灰。抽屉滑轨松脱，开合时发出短促的摩擦声。"
    calls = []

    def handler(_request):
        calls.append(1)
        return completion(repeated)

    model = model_with(handler)
    text = model.narrate(
        {"kind": "case_action", "action_id": "inspect_fangsheng_room", "label": "查看方笙住处"},
        {"outcome": "partial", "total": 7},
        previous_narratives=[repeated],
    )

    assert len(calls) == 2
    assert text == "你找到了苗雨留下的生活痕迹，但花了太多时间，楼里的项目终端正在同步清理。"


def test_repetition_retry_accepts_different_text():
    """重试产出不同文本时采用重试结果，不再回退。"""
    repeated = "你俯身翻检桌面，指尖触到一层薄灰。抽屉滑轨松脱，开合时发出短促的摩擦声。"
    outputs = iter([repeated, "门轴发出一声轻响，走廊尽头的指示灯忽明忽暗。你把手里的记录折好。"])
    calls = []

    def handler(_request):
        calls.append(1)
        return completion(next(outputs))

    fresh = "门轴发出一声轻响，走廊尽头的指示灯忽明忽暗。你把手里的记录折好。"
    model = model_with(handler)
    text = model.narrate(
        {"kind": "case_action", "action_id": "inspect_fangsheng_room", "label": "查看方笙住处"},
        {"outcome": "partial", "total": 7},
        previous_narratives=[repeated],
    )

    assert len(calls) == 2
    assert text == fresh


def test_empty_context_is_stable():
    """没有事件或认知时仍返回稳定结构，不抛出异常。"""
    context = build_narrative_context(
        [], {"location": "OC-01", "phase": "unoffered", "clues": []}, [], None
    )
    assert context["当前地点"].startswith("灰区事务所")
    assert context["在场人物"] == ["唐葵"]
    assert context["最近行动"] == []
    assert context["玩家已知线索"] == []


class RecordingModel(SimulatedModel):
    """记录游戏服务实际传入的上下文与最近叙事。"""

    def __init__(self):
        super().__init__()
        self.calls = []

    def narrate(self, intent, roll, context=None, previous_narratives=None, action_content=None):
        """保存参数后沿用确定性模拟叙事。"""
        self.calls.append({
            "context": context,
            "previous_narratives": previous_narratives,
        })
        return super().narrate(intent, roll)


def test_game_service_passes_context_and_previous_narrative(tmp_path):
    """游戏服务提交后构建上下文，并把上一条叙事交给模型。"""
    model = RecordingModel()
    service, _ = make_service(tmp_path, model)
    game_id = service.create_game("江逢")["id"]

    first = service.act(game_id, "接受方笙的委托", "request-0")
    service.act(game_id, "和唐葵谈谈", "request-1")

    assert len(model.calls) == 2
    second_call = model.calls[1]
    assert second_call["context"]["当前地点"].startswith("灰区事务所")
    assert second_call["context"]["最近行动"][0]["行动"] == "接受方笙的委托"
    assert second_call["previous_narratives"] == [first["narrative"]]
    assert SECRET_TRUTH not in json.dumps(second_call["context"], ensure_ascii=False)
    assert context_size(second_call["context"]) <= MAX_CONTEXT_CHARS
