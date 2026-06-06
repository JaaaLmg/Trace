# OpenAI 真客户端：实现 llm.py 的 LLMClient 协议（complete(messages)->LLMResponse）。
# 主线只走官方 Responses API；中转站/profile/chat fallback 不放进核心路径。
from __future__ import annotations

import os
from typing import Optional

import httpx

from app.agents.llm import LLMResponse, Message, estimate_tokens

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-5"


class OpenAILLM:
    """走 OpenAI Responses API 的 LLMClient 实现。

    - 凭据：默认从 TRACE_LLM_API_KEY 读取；兼容 OPENAI_API_KEY。
    - 地址：默认 https://api.openai.com/v1；必要时可用 TRACE_LLM_BASE_URL / OPENAI_BASE_URL 覆盖。
    - client 可注入：单测用 httpx.MockTransport / stub 顶替，不打网络。
    """

    def __init__(
        self,
        model: Optional[str] = None,
        *,
        temperature: Optional[float] = None,
        max_output_tokens: int = 4096,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        timeout: float = 120.0,
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
        self._client = client or httpx.Client(timeout=timeout)

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

        resp = self._client.post(self._endpoint, headers=self._headers(), json=payload)
        if hasattr(resp, "raise_for_status"):
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise RuntimeError(_format_http_error(e.response, self.api_key)) from e
        data = resp.json()

        text = _extract_response_text(data)
        tokens = _extract_usage_tokens(data) or (
            sum(estimate_tokens(m.content) for m in messages) + estimate_tokens(text)
        )
        return LLMResponse(text=text, tokens=tokens)

    def list_models(self) -> list[str]:
        resp = self._client.get(_models_endpoint(self.base_url), headers=self._headers())
        if hasattr(resp, "raise_for_status"):
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise RuntimeError(_format_http_error(e.response, self.api_key)) from e
        data = resp.json()
        items = data.get("data", data if isinstance(data, list) else [])
        ids: list[str] = []
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                ids.append(item["id"])
            elif isinstance(item, str):
                ids.append(item)
        return sorted(ids)

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


def _format_http_error(resp: httpx.Response, api_key: Optional[str]) -> str:
    status = f"{resp.status_code} {resp.reason_phrase}".strip()
    body = _redact(resp.text.strip(), api_key)
    if len(body) > 500:
        body = body[:497] + "..."
    if body:
        return f"OpenAI API HTTP {status}: {body}"
    return f"OpenAI API HTTP {status}"


def _redact(text: str, secret: Optional[str]) -> str:
    if secret:
        text = text.replace(secret, "[redacted]")
    return text


def _models_endpoint(base_url: str) -> str:
    if base_url.endswith("/models"):
        return base_url
    if base_url.endswith("/responses"):
        base_url = base_url[: -len("/responses")]
    return f"{base_url}/models"
