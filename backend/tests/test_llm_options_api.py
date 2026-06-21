from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import create_app


def test_llm_options_exposes_mock_option_from_runtime_config():
    app = create_app(initialize=False)

    with TestClient(app) as client:
        response = client.get("/api/v1/llm-options")

    assert response.status_code == 200
    payload = response.json()
    assert payload["default_option_id"] == "mock"
    assert payload["config_status"] == "ok"
    assert payload["options"] == [
        {
            "id": "mock",
            "label": "MockLLM / mock-1",
            "kind": "mock",
            "provider": "mock",
            "model": "mock-1",
            "is_mock": True,
            "selectable": True,
            "credential_status": "not_required",
            "config_source": "runtime_config",
            "base_url_configured": False,
            "reason": None,
        }
    ]


def test_llm_options_exposes_configured_real_llm_without_secret_values(tmp_path, monkeypatch):
    config_path = tmp_path / "llm.config.json"
    config_path.write_text(
        json.dumps(
            {
                "provider": "openai_chat_compat",
                "model": "gpt-test",
                "api_key": "sk-test-secret",
                "base_url": "https://llm.example.invalid/v1",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TRACE_LLM_CONFIG_FILE", str(config_path))
    app = create_app(initialize=False)

    with TestClient(app) as client:
        response = client.get("/api/v1/llm-options")

    assert response.status_code == 200
    payload = response.json()
    assert payload["default_option_id"] == "mock"
    options = {option["id"]: option for option in payload["options"]}
    assert options["mock"]["selectable"] is True
    assert options["configured-real"] == {
        "id": "configured-real",
        "label": "openai_chat_compat / gpt-test",
        "kind": "configured",
        "provider": "openai_chat_compat",
        "model": "gpt-test",
        "is_mock": False,
        "selectable": True,
        "credential_status": "configured",
        "config_source": "runtime_config",
        "base_url_configured": True,
        "reason": None,
    }
    assert "sk-test-secret" not in response.text
    assert "https://llm.example.invalid" not in response.text


def test_llm_options_marks_real_llm_unselectable_without_api_key(tmp_path, monkeypatch):
    config_path = tmp_path / "llm.config.json"
    config_path.write_text(
        json.dumps({"provider": "openai_chat_compat", "model": "gpt-test"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("TRACE_LLM_CONFIG_FILE", str(config_path))
    app = create_app(initialize=False)

    with TestClient(app) as client:
        response = client.get("/api/v1/llm-options")

    assert response.status_code == 200
    payload = response.json()
    configured = {option["id"]: option for option in payload["options"]}["configured-real"]
    assert configured["selectable"] is False
    assert configured["credential_status"] == "missing_api_key"
    assert configured["reason"] == "api_key_missing"


def test_llm_options_config_error_is_sanitized(tmp_path, monkeypatch):
    config_path = tmp_path / "llm.config.json"
    config_path.write_text(
        '{"provider": "openai_chat_compat", "api_key": "sk-should-not-leak",',
        encoding="utf-8",
    )
    monkeypatch.setenv("TRACE_LLM_CONFIG_FILE", str(config_path))
    app = create_app(initialize=False)

    with TestClient(app) as client:
        response = client.get("/api/v1/llm-options")

    assert response.status_code == 200
    assert response.json()["config_status"] == "error"
    assert response.json()["config_error"] == "config_parse_failed"
    assert "sk-should-not-leak" not in response.text
    assert str(config_path) not in response.text
