# OpenAI Chat Completions 兼容客户端：DeepSeek/Qwen/兼容网关可走这条薄 adapter。
# HTTP 调用、瞬态重试、错误脱敏统一走 llm_http，与官方 Responses adapter 共用一套。
from __future__ import annotations

import os
import re
from typing import Optional

import httpx

from app.agents.llm import LLMResponse, Message, estimate_tokens
from app.agents.llm_http import DEFAULT_MAX_OUTPUT_TOKENS, request_json
from app.core.errors import ErrorCode, TraceError


class OpenAIChatCompatLLM:
    """走 OpenAI-compatible `/chat/completions` 的 LLMClient 实现。

    - 凭据：默认从 TRACE_LLM_API_KEY 读取；兼容 OPENAI_CHAT_COMPAT_API_KEY / OPENAI_API_KEY。
    - 地址：必须显式提供 base URL，或设置 TRACE_LLM_BASE_URL / OPENAI_CHAT_COMPAT_BASE_URL。
    - 瞬态错误（连接抖动 / 429 / 5xx）由 llm_http 退避重试；4xx 快速失败。
    - client 可注入：单测用 httpx.MockTransport / stub 顶替，不打网络。
    - close() / 上下文管理：只关自己创建的 client，注入的 client 由调用方负责。
    """

    def __init__(
        self,
        model: Optional[str] = None,
        *,
        temperature: Optional[float] = None,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 120.0,
        max_retries: int = 2,
        retry_backoff: float = 0.5,
        client: Optional[object] = None,
    ):
        env_model = (
            os.environ.get("TRACE_LLM_MODEL")
            or os.environ.get("OPENAI_CHAT_COMPAT_MODEL")
            or os.environ.get("OPENAI_MODEL")
        )
        self.model = model or env_model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.api_key = (
            api_key
            or os.environ.get("TRACE_LLM_API_KEY")
            or os.environ.get("OPENAI_CHAT_COMPAT_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )
        raw_base = (
            base_url
            or os.environ.get("TRACE_LLM_BASE_URL")
            or os.environ.get("OPENAI_CHAT_COMPAT_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
        )
        if not raw_base:
            raise ValueError("openai_chat_compat 需要 --base-url 或 TRACE_LLM_BASE_URL/OPENAI_CHAT_COMPAT_BASE_URL")
        self.base_url = raw_base.rstrip("/")
        self._endpoint = _chat_endpoint(self.base_url)
        self._responses_endpoint = _responses_endpoint(self.base_url)
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def complete(self, messages: list[Message], **params) -> LLMResponse:
        if not self.model:
            raise ValueError("openai_chat_compat 需要 --model 或 TRACE_LLM_MODEL/OPENAI_CHAT_COMPAT_MODEL")
        temperature = params.get("temperature", self.temperature)
        last_error: TraceError | None = None
        for endpoint, payload, error_label in _request_variants(
            self.model,
            messages,
            max_output_tokens=self.max_output_tokens,
            temperature=temperature,
            chat_endpoint=self._endpoint,
            responses_endpoint=self._responses_endpoint,
        ):
            try:
                data = request_json(
                    self._client,
                    "POST",
                    endpoint,
                    headers=self._headers(),
                    json_body=payload,
                    error_label=error_label,
                    api_key=self.api_key,
                    max_retries=self._max_retries,
                    backoff=self._retry_backoff,
                )
            except TraceError as exc:
                last_error = exc
                if _should_fallback_to_alt_shape(exc):
                    continue
                raise

            text = _extract_text(data)
            # 响应被截断（finish_reason=length）且无文本：max_tokens 太小。给可定位错误，
            # 而不是让空串去撞下游笼统的「JSON 解析失败」。
            if not text and _finish_reason(data) == "length":
                raise TraceError(
                    ErrorCode.INVALID_MODEL_OUTPUT,
                    f"兼容端点响应被截断（finish_reason=length）：未产出文本；"
                    f"max_tokens（当前 {self.max_output_tokens}）可能过小，请调大",
                )
            tokens = _extract_usage_tokens(data) or (
                sum(estimate_tokens(m.content) for m in messages) + estimate_tokens(text)
            )
            return LLMResponse(text=text, tokens=tokens)

        assert last_error is not None
        raise last_error

    def list_models(self) -> list[str]:
        # 列模型是交互命令，失败就报错，不重试
        data = request_json(
            self._client,
            "GET",
            _models_endpoint(self.base_url),
            headers=self._headers(),
            error_label="OpenAI-compatible Chat API",
            api_key=self.api_key,
            max_retries=0,
        )
        items = data.get("data", data if isinstance(data, list) else [])
        ids: list[str] = []
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                ids.append(item["id"])
            elif isinstance(item, str):
                ids.append(item)
        return sorted(ids)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers


def _chat_endpoint(base_url: str) -> str:
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def _responses_endpoint(base_url: str) -> str:
    if base_url.endswith("/responses"):
        return base_url
    return f"{base_url}/responses"


def _message_to_chat(message: Message) -> dict:
    role = message.role if message.role in {"system", "user", "assistant", "developer"} else "user"
    if role == "developer":
        role = "system"
    return {"role": role, "content": message.content}


def _message_to_input(message: Message) -> dict:
    role = message.role if message.role in {"user", "assistant"} else "user"
    return {
        "type": "message",
        "role": role,
        "content": [{"type": "input_text", "text": message.content}],
    }


def _response_instructions(messages: list[Message]) -> str:
    parts = [m.content for m in messages if m.role in {"system", "developer"} and m.content]
    return "\n\n".join(parts)


def _request_variants(
    model: str,
    messages: list[Message],
    *,
    max_output_tokens: int,
    temperature: Optional[float],
    chat_endpoint: str,
    responses_endpoint: str,
) -> list[tuple[str, dict, str]]:
    chat_payload = {
        "model": model,
        "messages": [_message_to_chat(m) for m in messages],
        "max_tokens": max_output_tokens,
    }
    if temperature is not None:
        chat_payload["temperature"] = temperature

    responses_payload = {
        "model": model,
        "input": [_message_to_input(m) for m in messages if m.role not in {"system", "developer"}],
        "max_output_tokens": max_output_tokens,
        "store": False,
    }
    instructions = _response_instructions(messages)
    if instructions:
        responses_payload["instructions"] = instructions
    if temperature is not None:
        responses_payload["temperature"] = temperature

    if _model_prefers_responses(model):
        return [
            (responses_endpoint, responses_payload, "OpenAI-compatible Responses API"),
            (chat_endpoint, chat_payload, "OpenAI-compatible Chat API"),
        ]
    return [
        (chat_endpoint, chat_payload, "OpenAI-compatible Chat API"),
        (responses_endpoint, responses_payload, "OpenAI-compatible Responses API"),
    ]


def _model_prefers_responses(model: str) -> bool:
    normalized = model.strip().lower()
    return bool(re.match(r"^(gpt-5(\.|$)|o\d)", normalized))


def _should_fallback_to_alt_shape(exc: TraceError) -> bool:
    text = (exc.message or "").lower()
    return exc.code == ErrorCode.LLM_PROVIDER_ERROR and (
        "http 400" in text
        or "invalid_request_error" in text
        or "upstream_rejected_request" in text
        or "不符合当前接口要求" in text
        or "unsupported" in text
        or "unrecognized request argument" in text
    )


def _extract_text(data: dict) -> str:
    text = _extract_chat_text(data)
    if text:
        return text
    return _extract_response_text(data)


def _extract_chat_text(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    first = choices[0]
    message = first.get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                chunks.append(item["text"])
        return "".join(chunks)
    if isinstance(first.get("text"), str):
        return first["text"]
    return ""


def _extract_response_text(data: dict) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]

    chunks: list[str] = []
    for item in data.get("output", []) or []:
        for content in item.get("content", []) or []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                ctype = content.get("type")
                if ctype in {"output_text", "text"}:
                    chunks.append(content["text"])
    return "".join(chunks)


def _finish_reason(data: dict) -> Optional[str]:
    choices = data.get("choices") or []
    if not choices:
        return None
    return choices[0].get("finish_reason")


def _extract_usage_tokens(data: dict) -> int:
    usage = data.get("usage") or {}
    total = usage.get("total_tokens")
    if isinstance(total, int):
        return total
    prompt = usage.get("prompt_tokens", 0) or 0
    completion = usage.get("completion_tokens", 0) or 0
    return int(prompt) + int(completion)


def _models_endpoint(base_url: str) -> str:
    if base_url.endswith("/models"):
        return base_url
    if base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")]
    return f"{base_url}/models"
