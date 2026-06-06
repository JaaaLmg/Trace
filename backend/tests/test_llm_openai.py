# OpenAILLM 单测：注入 httpx.MockTransport，不打网络、不要钱。
from __future__ import annotations

import json

import httpx
import pytest

from app.agents.llm import Message
from app.agents.llm_openai import OpenAILLM


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_openai_responses_request_shape_and_auth():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["x_api_key"] = request.headers.get("X-API-Key")
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"output_text": "{}", "usage": {"input_tokens": 7, "output_tokens": 3}})

    llm = OpenAILLM(
        "gpt-5",
        api_key="sk-test",
        base_url="https://api.openai.test/v1",
        temperature=0.2,
        max_output_tokens=123,
        reasoning_effort="high",
        client=_client(handler),
    )
    resp = llm.complete([Message("system", "SYS"), Message("developer", "DEV"), Message("user", "U")])

    assert seen["url"] == "https://api.openai.test/v1/responses"
    assert seen["auth"] == "Bearer sk-test"
    assert seen["x_api_key"] is None
    body = seen["body"]
    assert body["model"] == "gpt-5"
    assert body["temperature"] == 0.2
    assert body["reasoning"] == {"effort": "high"}
    assert body["store"] is False
    assert body["max_output_tokens"] == 123
    assert body["instructions"] == "SYS\n\nDEV"
    assert body["input"] == [
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "U"}]},
    ]
    assert resp.text == "{}"
    assert resp.tokens == 10


def test_openai_omits_temperature_when_none():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"output_text": "{}"})

    OpenAILLM(api_key="sk-test", temperature=None, client=_client(handler)).complete([Message("user", "U")])

    assert "temperature" not in seen["body"]


def test_openai_uses_trace_env_defaults(monkeypatch):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"output_text": "{}"})

    monkeypatch.setenv("TRACE_LLM_MODEL", "env-model")
    monkeypatch.setenv("TRACE_LLM_API_KEY", "env-key")
    monkeypatch.setenv("TRACE_LLM_BASE_URL", "https://api.env.test/v1")

    OpenAILLM(client=_client(handler)).complete([Message("user", "U")])

    assert seen["url"] == "https://api.env.test/v1/responses"
    assert seen["auth"] == "Bearer env-key"
    assert seen["body"]["model"] == "env-model"


def test_custom_base_url_still_uses_responses_endpoint():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"output_text": "{}"})

    OpenAILLM(api_key="sk-test", base_url="https://gateway.test/v1", client=_client(handler)).complete(
        [Message("user", "U")]
    )

    assert seen["url"] == "https://gateway.test/v1/responses"


def test_openai_endpoint_accepts_responses_url():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"output_text": "{}"})

    OpenAILLM(api_key="sk-test", base_url="https://api.openai.test/v1/responses", client=_client(handler)).complete(
        [Message("user", "U")]
    )

    assert seen["url"] == "https://api.openai.test/v1/responses"


def test_openai_extracts_output_array_text_and_total_tokens():
    def handler(_request):
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "{"}, {"type": "output_text", "text": "}"}],
                    }
                ],
                "usage": {"total_tokens": 42},
            },
        )

    resp = OpenAILLM(api_key="sk-test", client=_client(handler)).complete([Message("user", "U")])

    assert resp.text == "{}"
    assert resp.tokens == 42


def test_openai_falls_back_to_local_token_estimate_without_usage():
    def handler(_request):
        return httpx.Response(200, json={"output_text": "abcd"})

    resp = OpenAILLM(api_key="sk-test", client=_client(handler)).complete([Message("user", "abcd")])

    assert resp.text == "abcd"
    assert resp.tokens == 2


def test_openai_http_error_is_readable_and_redacted():
    def handler(_request):
        return httpx.Response(401, text='{"error":"bad key sk-test"}')

    llm = OpenAILLM(api_key="sk-test", base_url="https://api.openai.test/v1", client=_client(handler))

    with pytest.raises(RuntimeError) as exc:
        llm.complete([Message("user", "U")])

    text = str(exc.value)
    assert "OpenAI API HTTP 401 Unauthorized" in text
    assert "bad key" in text
    assert "sk-test" not in text
    assert "[redacted]" in text


def test_list_models_uses_models_endpoint_and_sorts_ids():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"data": [{"id": "z-model"}, {"id": "a-model"}]})

    llm = OpenAILLM(api_key="sk-test", base_url="https://api.openai.test/v1/responses", client=_client(handler))

    assert llm.list_models() == ["a-model", "z-model"]
    assert seen["url"] == "https://api.openai.test/v1/models"
    assert seen["auth"] == "Bearer sk-test"
