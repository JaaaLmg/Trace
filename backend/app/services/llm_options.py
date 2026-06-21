from __future__ import annotations

from typing import Literal

from app.agents.llm_config import LLMRuntimeConfig, load_llm_config
from app.schemas.api_llm_options import LlmOptionOut, LlmOptionsOut


def _mock_option(*, source: Literal["built_in", "runtime_config"] = "built_in", model: str = "mock-1") -> LlmOptionOut:
    return LlmOptionOut(
        id="mock",
        label="MockLLM / mock-1",
        kind="mock",
        provider="mock",
        model=model or "mock-1",
        is_mock=True,
        selectable=True,
        credential_status="not_required",
        config_source=source,
    )


def _configured_option(config: LLMRuntimeConfig) -> LlmOptionOut:
    has_api_key = bool(config.api_key)
    return LlmOptionOut(
        id="configured-real",
        label=f"{config.provider} / {config.model}",
        kind="configured",
        provider=config.provider,
        model=config.model,
        is_mock=False,
        selectable=has_api_key,
        credential_status="configured" if has_api_key else "missing_api_key",
        config_source="runtime_config",
        base_url_configured=bool(config.base_url),
        reason=None if has_api_key else "api_key_missing",
    )


def get_llm_options() -> LlmOptionsOut:
    options = [_mock_option()]
    try:
        config = load_llm_config()
    except Exception as exc:
        return LlmOptionsOut(
            default_option_id="mock",
            config_status="error",
            config_error=_safe_config_error(exc),
            options=options,
        )

    if config is None:
        return LlmOptionsOut(default_option_id="mock", config_status="missing", options=options)

    if config.provider == "mock":
        return LlmOptionsOut(
            default_option_id="mock",
            config_status="ok",
            options=[_mock_option(source="runtime_config", model=config.model)],
        )

    options.append(_configured_option(config))
    return LlmOptionsOut(default_option_id="mock", config_status="ok", options=options)


def validate_llm_override_against_options(provider: str | None, model: str | None) -> None:
    if not provider or not model:
        return
    options = get_llm_options()
    for option in options.options:
        if option.selectable and option.provider == provider and option.model == model:
            return
    raise ValueError("llm_override must match a selectable LLM option")


def _safe_config_error(exc: Exception) -> str:
    name = type(exc).__name__
    text = str(exc).lower()
    if "不存在" in text or "not exist" in text or "no such file" in text:
        return "config_file_missing"
    if name in {"JSONDecodeError"}:
        return "config_parse_failed"
    if "provider" in text:
        return "unsupported_provider"
    return "config_load_failed"
