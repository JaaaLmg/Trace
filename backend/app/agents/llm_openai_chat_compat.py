# OpenAI Chat Completions 兼容客户端：DeepSeek/Qwen/兼容网关可走这条薄 adapter。
from __future__ import annotations

import os
from typing import Optional

import httpx

from app.agents.llm import LLMResponse, Message, estimate_tokens


class OpenAIChatCompatLLM:
    """走 OpenAI-compatible `/chat/completions` 的 LLMClient 实现。

    - 凭据：默认从 TRACE_LLM_API_KEY 读取；兼容 OPENAI_CHAT_COMPAT_API_KEY / OPENAI_API_KEY。
    - 地址：必须显式提供 base URL，或设置 TRACE_LLM_BASE_URL / OPENAI_CHAT_COMPAT_BASE_URL。
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
        timeout: float = 120.0,
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
        self._client = client or httpx.Client(timeout=timeout)

    def complete(self, messages: list[Message], **params) -> LLMResponse:
        if not self.model:
            raise ValueError("openai_chat_compat 需要 --model 或 TRACE_LLM_MODEL/OPENAI_CHAT_COMPAT_MODEL")
        payload = {
            "model": self.model,
            "messages": [_message_to_chat(m) for m in messages],
            "max_tokens": self.max_output_tokens,
        }
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

        text = _extract_chat_text(data)
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


def _chat_endpoint(base_url: str) -> str:
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def _message_to_chat(message: Message) -> dict:
    role = message.role if message.role in {"system", "user", "assistant", "developer"} else "user"
    if role == "developer":
        role = "system"
    return {"role": role, "content": message.content}


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


def _extract_usage_tokens(data: dict) -> int:
    usage = data.get("usage") or {}
    total = usage.get("total_tokens")
    if isinstance(total, int):
        return total
    prompt = usage.get("prompt_tokens", 0) or 0
    completion = usage.get("completion_tokens", 0) or 0
    return int(prompt) + int(completion)


def _format_http_error(resp: httpx.Response, api_key: Optional[str]) -> str:
    status = f"{resp.status_code} {resp.reason_phrase}".strip()
    body = _redact(resp.text.strip(), api_key)
    if len(body) > 500:
        body = body[:497] + "..."
    if body:
        return f"OpenAI-compatible Chat API HTTP {status}: {body}"
    return f"OpenAI-compatible Chat API HTTP {status}"


def _redact(text: str, secret: Optional[str]) -> str:
    if secret:
        text = text.replace(secret, "[redacted]")
    return text


def _models_endpoint(base_url: str) -> str:
    if base_url.endswith("/models"):
        return base_url
    if base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")]
    return f"{base_url}/models"
