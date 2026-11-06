"""程序说明：先行验证第七阶段 Provider 配置、在线意图解析兜底与叙事失败契约。"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.llm_model import ProviderModel
from app.main import create_app
from app.model import SimulatedModel, SimulationError
from app.provider_config import load_provider_config


LEGAL_ACTION = {
    "id": "inspect_fangsheng_room",
    "label": "查看方笙住处",
    "aliases": ["方笙住处", "检查房间"],
    "tendency": "洞察",
    "requires_roll": True,
    "modifier": 1,
}


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


def completion(content, status=200):
    """构造 OpenAI 兼容响应。"""
    payload = {
        "model": "qwen-test",
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
    }
    return httpx.Response(status, json=payload)


def model_with(handler, **config_overrides):
    """建立只走模拟传输的在线模型。"""
    config = load_provider_config(environ=provider_env(**config_overrides))
    return ProviderModel(
        config,
        fallback=SimulatedModel(),
        transport=httpx.MockTransport(handler),
        sleep=lambda _seconds: None,
    )


def test_provider_config_reads_catalog(tmp_path):
    """读取编号目录，并保留可公开信息。"""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(f"{key}={value}" for key, value in provider_env().items()),
        encoding="utf-8",
    )
    config = load_provider_config(env_file, environ={})
    assert config.provider_name == "dashscope"
    assert config.model_name == "qwen-test"
    assert config.max_retries == 1
    assert config.public_info() == {"provider": "dashscope", "model_name": "qwen-test"}
    assert "test-secret-key" not in json.dumps(config.public_info(), ensure_ascii=False)


def test_environment_overrides_env_file(tmp_path):
    """进程环境变量优先于文件，便于临时切换 Provider。"""
    env_file = tmp_path / ".env"
    env_file.write_text("AI_CURRENT_PROVIDER=2\nAI_PROVIDER_2_NAME=deepseek\n", encoding="utf-8")
    config = load_provider_config(env_file, environ=provider_env())
    assert config.provider_name == "dashscope"


def test_missing_provider_returns_none():
    """无当前 Provider 时返回 None，由应用回退模拟模型。"""
    assert load_provider_config(environ={}) is None


def test_invalid_base_url_rejected_without_leaking_key():
    """非法地址明确失败，错误信息不得包含密钥。"""
    with pytest.raises(ValueError) as excinfo:
        load_provider_config(environ=provider_env(AI_PROVIDER_1_BASE_URL="ftp://example.test"))
    assert "test-secret-key" not in str(excinfo.value)
    assert "BASE_URL" in str(excinfo.value)


def test_parse_uses_program_action_fields():
    """模型只提供行动编号，标签与机械字段必须取自程序目录。"""
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return completion('{"kind":"case_action","action_id":"inspect_fangsheng_room","label":"伪造标签"}')

    model = model_with(handler)
    intent = model.parse_action("看看方笙的房间", [LEGAL_ACTION])
    assert intent["action_id"] == "inspect_fangsheng_room"
    assert intent["label"] == "查看方笙住处"
    assert intent["tendency"] == "洞察"
    assert intent["modifier"] == 1
    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["auth"] == "Bearer test-secret-key"
    assert captured["body"]["model"] == "qwen-test"


def test_parse_unknown_action_falls_back():
    """未知行动编号回退本地解析。"""

    def handler(_request):
        return completion('{"kind":"case_action","action_id":"not_legal"}')

    intent = model_with(handler).parse_action("检查现场", [LEGAL_ACTION])
    assert intent["kind"] == "inspect"


def test_parse_http_error_falls_back():
    """HTTP 失败不阻断行动解析。"""

    def handler(_request):
        return httpx.Response(500, json={"error": "boom"})

    intent = model_with(handler).parse_action("检查现场", [LEGAL_ACTION])
    assert intent["kind"] == "inspect"


def test_narrate_trims_fence_and_quotes():
    """叙事清理代码块围栏与引号，只保留正文。"""

    def handler(_request):
        return completion("```\n你检查了房间的门锁和桌面，确认这里最近有人匆忙离开。\n```")

    model = model_with(handler)
    text = model.narrate(
        {"kind": "case_action", "action_id": "inspect_fangsheng_room", "label": "查看方笙住处"},
        {"outcome": "success", "total": 9},
    )
    assert text == "你检查了房间的门锁和桌面，确认这里最近有人匆忙离开。"
    assert "```" not in text


def test_narrate_prompt_treats_reference_as_boundary():
    """提示词要求受限扩写：固定要点是事实边界，不得照抄，可补感官细节。"""
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return completion("你俯身翻检桌面，指尖触到一层薄灰。抽屉滑轨松脱，开合时发出短促的摩擦声。")

    model = model_with(handler)
    text = model.narrate(
        {
            "kind": "case_action",
            "action_id": "inspect_fangsheng_room",
            "label": "查看方笙住处",
            "tendency": "洞察",
        },
        {"outcome": "partial", "total": 7},
    )
    assert "薄灰" in text

    messages = captured["body"]["messages"]
    system = messages[0]["content"]
    fact = json.loads(messages[1]["content"])
    assert "不可改变的事实边界" in system
    assert "不得照抄" in system
    assert "感官细节" in system
    assert "固定要点（事实边界，不可照抄）" in fact
    assert fact["判定结果"] == "有代价成功"
    assert fact["倾向"] == "洞察"


def test_narrate_failure_raises_simulation_error_without_secret():
    """叙事失败转为待重试，错误信息不得泄露密钥。"""

    def handler(_request):
        return httpx.Response(401, json={"error": "invalid key"})

    model = model_with(handler)
    with pytest.raises(SimulationError) as excinfo:
        model.narrate(
            {"kind": "case_action", "action_id": "inspect_fangsheng_room", "label": "查看方笙住处"},
            {"outcome": "success", "total": 9},
        )
    assert "test-secret-key" not in str(excinfo.value)
    assert "重试" in str(excinfo.value)


def test_health_reports_only_public_provider_info(tmp_path):
    """健康接口只暴露模型来源，不返回密钥或地址。"""
    model = model_with(lambda _request: completion("{}"))
    client = TestClient(create_app(tmp_path / "health.db", model=model))
    data = client.get("/api/health").json()
    assert data["model"] == "provider"
    assert data["provider"] == "dashscope"
    assert data["model_name"] == "qwen-test"
    assert "test-secret-key" not in json.dumps(data)
    assert "example.test" not in json.dumps(data)
