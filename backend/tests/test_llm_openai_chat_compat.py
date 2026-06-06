# OpenAI Chat Completions 兼容 adapter 单测：MockTransport，不打真实网络。
from __future__ import annotations

import json

import httpx
import pytest

from app.agents.llm import Message
from app.agents.llm_factory import create_llm, normalize_provider, resolve_model
from app.agents.llm_openai import OpenAILLM
from app.agents.llm_openai_chat_compat import OpenAIChatCompatLLM


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_chat_compat_request_shape_and_auth():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}], "usage": {"total_tokens": 11}})

    llm = OpenAIChatCompatLLM(
        "deepseek-chat",
        api_key="sk-test",
        base_url="https://compat.test/v1",
        temperature=0.3,
        max_output_tokens=321,
        client=_client(handler),
    )
    resp = llm.complete([Message("system", "SYS"), Message("developer", "DEV"), Message("user", "U")])

    assert seen["url"] == "https://compat.test/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"] == {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "SYS"},
            {"role": "system", "content": "DEV"},
            {"role": "user", "content": "U"},
        ],
        "max_tokens": 321,
        "temperature": 0.3,
    }
    assert resp.text == "{}"
    assert resp.tokens == 11


def test_chat_compat_accepts_full_chat_completions_url():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    OpenAIChatCompatLLM(
        "qwen-plus",
        api_key="sk-test",
        base_url="https://compat.test/v1/chat/completions",
        client=_client(handler),
    ).complete([Message("user", "U")])

    assert seen["url"] == "https://compat.test/v1/chat/completions"


def test_chat_compat_uses_trace_env_defaults(monkeypatch):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setenv("TRACE_LLM_MODEL", "env-chat-model")
    monkeypatch.setenv("TRACE_LLM_API_KEY", "env-key")
    monkeypatch.setenv("TRACE_LLM_BASE_URL", "https://env-chat.test/v1")

    OpenAIChatCompatLLM(client=_client(handler)).complete([Message("user", "U")])

    assert seen["url"] == "https://env-chat.test/v1/chat/completions"
    assert seen["auth"] == "Bearer env-key"
    assert seen["body"]["model"] == "env-chat-model"


def test_chat_compat_requires_base_url_and_model():
    with pytest.raises(ValueError, match="base-url"):
        OpenAIChatCompatLLM("deepseek-chat", api_key="sk-test")

    llm = OpenAIChatCompatLLM(api_key="sk-test", base_url="https://compat.test/v1", client=_client(lambda _r: None))
    with pytest.raises(ValueError, match="model"):
        llm.complete([Message("user", "U")])


def test_chat_compat_extracts_list_content_and_estimates_tokens_without_usage():
    def handler(_request):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": [{"type": "text", "text": "{"}, {"type": "text", "text": "}"}]}}]},
        )

    resp = OpenAIChatCompatLLM(
        "compat-model",
        api_key="sk-test",
        base_url="https://compat.test/v1",
        client=_client(handler),
    ).complete([Message("user", "abcd")])

    assert resp.text == "{}"
    assert resp.tokens == 2


def test_chat_compat_http_error_is_readable_and_redacted():
    def handler(_request):
        return httpx.Response(401, text='{"error":"bad key sk-test"}')

    llm = OpenAIChatCompatLLM(
        "compat-model",
        api_key="sk-test",
        base_url="https://compat.test/v1",
        client=_client(handler),
    )

    with pytest.raises(RuntimeError) as exc:
        llm.complete([Message("user", "U")])

    text = str(exc.value)
    assert "OpenAI-compatible Chat API HTTP 401 Unauthorized" in text
    assert "bad key" in text
    assert "sk-test" not in text
    assert "[redacted]" in text


def test_chat_compat_list_models_strips_chat_endpoint():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"data": [{"id": "z-model"}, {"id": "a-model"}]})

    llm = OpenAIChatCompatLLM(
        base_url="https://compat.test/v1/chat/completions",
        api_key="sk-test",
        client=_client(handler),
    )

    assert llm.list_models() == ["a-model", "z-model"]
    assert seen["url"] == "https://compat.test/v1/models"


def test_llm_factory_routes_openai_and_chat_compat(monkeypatch):
    monkeypatch.setenv("TRACE_LLM_BASE_URL", "https://compat.test/v1")

    assert isinstance(create_llm("openai", "gpt-5"), OpenAILLM)
    assert isinstance(create_llm("openai_chat_compat", "deepseek-chat"), OpenAIChatCompatLLM)
    assert normalize_provider("openai-compatible-chat") == "openai_chat_compat"
    assert resolve_model("openai", None) == "gpt-5"

    with pytest.raises(ValueError, match="reasoning_effort"):
        create_llm("openai_chat_compat", "deepseek-chat", reasoning_effort="high")

    with pytest.raises(ValueError, match="未知 LLM provider"):
        create_llm("unknown", "model")
