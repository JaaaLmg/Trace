from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agents.llm_http import DEFAULT_MAX_OUTPUT_TOKENS
from app.agents.llm_factory import normalize_provider, resolve_model

_ENV_CONFIG_KEYS = (
    "TRACE_LLM_PROVIDER",
    "TRACE_LLM_MODEL",
    "TRACE_LLM_API_KEY",
    "TRACE_LLM_BASE_URL",
    "TRACE_LLM_TEMPERATURE",
    "TRACE_LLM_MAX_OUTPUT_TOKENS",
    "TRACE_LLM_REASONING_EFFORT",
    "OPENAI_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MAX_OUTPUT_TOKENS",
    "OPENAI_REASONING_EFFORT",
    "OPENAI_CHAT_COMPAT_MODEL",
    "OPENAI_CHAT_COMPAT_API_KEY",
    "OPENAI_CHAT_COMPAT_BASE_URL",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_config_path() -> Path:
    return _repo_root() / "backend" / "llm.config.json"


def _config_path() -> Path:
    override = os.environ.get("TRACE_LLM_CONFIG_FILE")
    if override:
        return Path(override).expanduser().resolve()
    return _default_config_path()


@dataclass(frozen=True)
class LLMRuntimeConfig:
    provider: str
    model: str
    api_key: str | None = None
    base_url: str | None = None
    temperature: float | None = None
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    reasoning_effort: str | None = None


def load_llm_config() -> LLMRuntimeConfig | None:
    path = _config_path()
    if path.exists():
        return _load_llm_config_file(path)
    if os.environ.get("TRACE_LLM_CONFIG_FILE"):
        raise ValueError(f"LLM 配置文件不存在: {path}")
    return _load_llm_config_env()


def _load_llm_config_file(path: Path) -> LLMRuntimeConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"LLM 配置文件必须是 JSON object: {path}")

    provider_raw = (_as_str(raw.get("provider")) or "openai_chat_compat").lower().replace("-", "_")
    provider = "mock" if provider_raw == "mock" else normalize_provider(provider_raw)
    model = _as_str(raw.get("model")) or ("mock-1" if provider == "mock" else resolve_model(provider, None))
    if not model:
        raise ValueError(f"LLM 配置缺少 model: {path}")

    return LLMRuntimeConfig(
        provider=provider,
        model=model,
        api_key=_as_str(raw.get("api_key")),
        base_url=_as_str(raw.get("base_url")),
        temperature=_as_float(raw.get("temperature")),
        max_output_tokens=_as_int(raw.get("max_output_tokens"), DEFAULT_MAX_OUTPUT_TOKENS),
        reasoning_effort=_as_str(raw.get("reasoning_effort")),
    )


def _load_llm_config_env() -> LLMRuntimeConfig | None:
    if not any(_as_str(os.environ.get(key)) for key in _ENV_CONFIG_KEYS):
        return None

    provider_raw = _env_provider_raw().lower().replace("-", "_")
    provider = "mock" if provider_raw == "mock" else normalize_provider(provider_raw)
    model = _env_model(provider)
    if not model:
        raise ValueError("LLM 环境变量缺少 model；请设置 TRACE_LLM_MODEL 或 provider 对应的模型变量")

    return LLMRuntimeConfig(
        provider=provider,
        model=model,
        api_key=_env_api_key(provider),
        base_url=_env_base_url(provider),
        temperature=_as_float(os.environ.get("TRACE_LLM_TEMPERATURE")),
        max_output_tokens=_as_int(
            os.environ.get("TRACE_LLM_MAX_OUTPUT_TOKENS") or os.environ.get("OPENAI_MAX_OUTPUT_TOKENS"),
            DEFAULT_MAX_OUTPUT_TOKENS,
        ),
        reasoning_effort=_as_str(
            os.environ.get("TRACE_LLM_REASONING_EFFORT") or os.environ.get("OPENAI_REASONING_EFFORT")
        ),
    )


def _env_provider_raw() -> str:
    explicit = _as_str(os.environ.get("TRACE_LLM_PROVIDER"))
    if explicit:
        return explicit
    if (
        _as_str(os.environ.get("OPENAI_CHAT_COMPAT_MODEL"))
        or _as_str(os.environ.get("OPENAI_CHAT_COMPAT_API_KEY"))
        or _as_str(os.environ.get("OPENAI_CHAT_COMPAT_BASE_URL"))
    ):
        return "openai_chat_compat"
    return "openai"


def _env_model(provider: str) -> str | None:
    if provider == "mock":
        return _as_str(os.environ.get("TRACE_LLM_MODEL")) or "mock-1"
    return resolve_model(provider, None)


def _env_api_key(provider: str) -> str | None:
    if provider == "openai_chat_compat":
        return _as_str(
            os.environ.get("TRACE_LLM_API_KEY")
            or os.environ.get("OPENAI_CHAT_COMPAT_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )
    return _as_str(os.environ.get("TRACE_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY"))


def _env_base_url(provider: str) -> str | None:
    if provider == "openai_chat_compat":
        return _as_str(
            os.environ.get("TRACE_LLM_BASE_URL")
            or os.environ.get("OPENAI_CHAT_COMPAT_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
        )
    return _as_str(os.environ.get("TRACE_LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL"))


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_int(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
