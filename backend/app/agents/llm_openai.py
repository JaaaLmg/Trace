# OpenAI 真客户端：实现 llm.py 的 LLMClient 协议（complete(messages)->LLMResponse）。
# 主线只走官方 Responses API；中转站/profile/chat fallback 不放进核心路径。
# HTTP 调用、瞬态重试、错误脱敏统一走 llm_http，两个 adapter 共用一套。
from __future__ import annotations

import os
from typing import Optional

import httpx

from app.agents.llm import LLMResponse, Message, estimate_tokens
from app.agents.llm_http import DEFAULT_MAX_OUTPUT_TOKENS, request_json
from app.core.errors import ErrorCode, TraceError

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-5"


class OpenAILLM:
    """走 OpenAI Responses API 的 LLMClient 实现。

    - 凭据：默认从 TRACE_LLM_API_KEY 读取；兼容 OPENAI_API_KEY。
    - 地址：默认 https://api.openai.com/v1；必要时可用 TRACE_LLM_BASE_URL / OPENAI_BASE_URL 覆盖。
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
        reasoning_effort: Optional[str] = None,
        timeout: float = 120.0,
        max_retries: int = 2,
        retry_backoff: float = 0.5,
        client: Optional[object] = None,
    ):
        env_model = os.environ.get("TRACE_LLM_MODEL") or os.environ.get("OPENAI_MODEL")
        self.model = model or env_model or DEFAULT_MODEL
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.api_key = api_key or os.environ.get("TRACE_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        raw_base = base_url or os.environ.get("TRACE_LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL
        self.base_url = raw_base.rstrip("/")
        self._endpoint = _responses_endpoint(self.base_url)
        self.reasoning_effort = reasoning_effort or os.environ.get("TRACE_LLM_REASONING_EFFORT") or os.environ.get(
            "OPENAI_REASONING_EFFORT"
        )
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def complete(self, messages: list[Message], **params) -> LLMResponse:
        payload = _build_payload(
            self.model,
            messages,
            self.max_output_tokens,
            params.get("reasoning_effort", self.reasoning_effort),
        )
        temperature = params.get("temperature", self.temperature)
        if temperature is not None:
            payload["temperature"] = temperature

        data = request_json(
            self._client,
            "POST",
            self._endpoint,
            headers=self._headers(),
            json_body=payload,
            error_label="OpenAI API",
            api_key=self.api_key,
            max_retries=self._max_retries,
            backoff=self._retry_backoff,
        )

        text = _extract_response_text(data)
        # 响应被截断（status=incomplete）：reasoning 模型常因推理 token 耗尽 max_output_tokens 而无输出。
        # 给出可定位的错误，而不是让空串去撞下游笼统的「JSON 解析失败」。
        if not text and data.get("status") == "incomplete":
            reason = (data.get("incomplete_details") or {}).get("reason", "unknown")
            raise TraceError(
                ErrorCode.INVALID_MODEL_OUTPUT,
                f"OpenAI 响应被截断（status=incomplete, reason={reason}）：未产出文本；"
                f"reasoning 模型可能耗尽 max_output_tokens（当前 {self.max_output_tokens}），请调大",
            )
        tokens = _extract_usage_tokens(data) or (
            sum(estimate_tokens(m.content) for m in messages) + estimate_tokens(text)
        )
        return LLMResponse(text=text, tokens=tokens)

    def list_models(self) -> list[str]:
        # 列模型是交互命令，失败就报错，不重试
        data = request_json(
            self._client,
            "GET",
            _models_endpoint(self.base_url),
            headers=self._headers(),
            error_label="OpenAI API",
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


def _responses_endpoint(base_url: str) -> str:
    if base_url.endswith("/responses"):
        return base_url
    return f"{base_url}/responses"


def _build_payload(
    model: str,
    messages: list[Message],
    max_output_tokens: int,
    reasoning_effort: Optional[str],
) -> dict:
    payload = {
        "model": model,
        "input": [_message_to_input(m) for m in messages if m.role not in {"system", "developer"}],
        "max_output_tokens": max_output_tokens,
        "store": False,
    }
    instructions = _response_instructions(messages)
    if instructions:
        payload["instructions"] = instructions
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}
    return payload


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


def _extract_response_text(data: dict) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]

    chunks: list[str] = []
    for item in data.get("output", []) or []:
        for content in item.get("content", []) or []:
            ctype = content.get("type")
            if ctype in {"output_text", "text"} and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "".join(chunks)


def _extract_usage_tokens(data: dict) -> int:
    usage = data.get("usage") or {}
    total = usage.get("total_tokens")
    if isinstance(total, int):
        return total
    prompt = usage.get("input_tokens", 0) or 0
    completion = usage.get("output_tokens", 0) or 0
    return int(prompt) + int(completion)


def _models_endpoint(base_url: str) -> str:
    if base_url.endswith("/models"):
        return base_url
    if base_url.endswith("/responses"):
        base_url = base_url[: -len("/responses")]
    return f"{base_url}/models"
