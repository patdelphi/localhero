"""程序说明：从 .env 读取 OpenAI 兼容 Provider 配置，只输出可公开信息，不打印密钥。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


@dataclass(frozen=True)
class ProviderConfig:
    """一个已校验的 Provider 与模型选择。"""

    provider_name: str
    base_url: str
    api_key: str
    model_name: str
    timeout_seconds: float = 180.0
    max_retries: int = 3
    max_output_tokens: int = 4096

    def public_info(self) -> dict:
        """返回可写入日志或健康接口的信息，不包含密钥与地址。"""
        return {"provider": self.provider_name, "model_name": self.model_name}


def load_provider_config(
    env_path: str | Path | None = None,
    environ: dict | None = None,
) -> ProviderConfig | None:
    """读取当前 Provider；缺失编号时返回 None，非法配置抛出 ValueError。"""
    values = _collect_values(env_path, environ)
    provider_id = values.get("AI_CURRENT_PROVIDER", "").strip()
    if not provider_id:
        return None
    if not provider_id.isdigit():
        raise ValueError("AI_CURRENT_PROVIDER 必须是正整数编号")

    model_id = values.get("AI_CURRENT_MODEL", "").strip()
    if not model_id:
        raise ValueError("缺少 AI_CURRENT_MODEL")

    prefix = f"AI_PROVIDER_{provider_id}"
    provider_name = values.get(f"{prefix}_NAME", "").strip()
    base_url = values.get(f"{prefix}_BASE_URL", "").strip()
    api_key = values.get(f"{prefix}_API_KEY", "").strip()
    model_key = f"AI_MODEL_{model_id.replace('.', '_')}_NAME"
    model_name = values.get(model_key, "").strip()

    if not provider_name:
        raise ValueError(f"缺少 {prefix}_NAME")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError(f"{prefix}_BASE_URL 必须是 http(s) 地址")
    if not model_name:
        raise ValueError(f"缺少 {model_key}")
    if not api_key and not _is_local_host(base_url):
        raise ValueError(f"{prefix}_API_KEY 不能为空")

    timeout_seconds = _bounded_float(values.get(f"{prefix}_TIMEOUT_SECONDS"), 180.0, 5.0, 600.0)
    max_retries = _bounded_int(values.get(f"{prefix}_MAX_RETRIES"), 3, 0, 5)
    max_output_tokens = _bounded_int(
        values.get(f"{prefix}_MAX_OUTPUT_TOKENS"), 4096, 256, 131072
    )
    return ProviderConfig(
        provider_name=provider_name,
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        model_name=model_name,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        max_output_tokens=max_output_tokens,
    )


def load_director_settings(
    env_path: str | Path | None = None,
    environ: dict | None = None,
) -> tuple[bool, int]:
    """读取情节导演默认开关与冷却间隔；默认关闭，间隔 2—50。"""
    values = _collect_values(env_path, environ)
    raw_enabled = values.get("AI_DIRECTOR_ENABLED", "").strip().lower()
    enabled = raw_enabled in {"1", "true", "yes", "on"}
    interval = _bounded_int(values.get("AI_DIRECTOR_INTERVAL"), 5, 2, 50)
    return enabled, interval


def _collect_values(env_path: str | Path | None, environ: dict | None) -> dict:
    """显式注入环境时以注入值为准，否则读取 .env 并被进程环境覆盖。"""
    if environ is None:
        values = _read_env_file(env_path or DEFAULT_ENV_PATH)
        values.update(os.environ)
        return values
    file_values = _read_env_file(env_path) if env_path else {}
    return {**file_values, **environ}


def _read_env_file(path: str | Path) -> dict:
    """读取简单 KEY=VALUE 文件，忽略注释与空行。"""
    env_path = Path(path)
    if not env_path.exists():
        return {}
    values = {}
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def _is_local_host(base_url: str) -> bool:
    """判断是否为本机或内网地址，允许本地 Provider 不填密钥。"""
    host = urlsplit(base_url).hostname or ""
    if host in {"127.0.0.1", "localhost", "::1"}:
        return True
    parts = host.split(".")
    if len(parts) == 4 and parts[0] in {"10", "192"}:
        return True
    return len(parts) == 4 and parts[0] == "172" and parts[1].isdigit() and 16 <= int(parts[1]) <= 31


def _bounded_int(raw: str | None, default: int, minimum: int, maximum: int) -> int:
    """解析并限制整数配置，非法值直接使用默认值。"""
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _bounded_float(raw: str | None, default: float, minimum: float, maximum: float) -> float:
    """解析并限制浮点配置，非法值直接使用默认值。"""
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))
