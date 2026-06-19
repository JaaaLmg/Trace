from __future__ import annotations

import json
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agents import llm_config
from app.db.session import get_engine
from app.main import create_app


def _clear_llm_env(monkeypatch):
    monkeypatch.delenv("TRACE_LLM_CONFIG_FILE", raising=False)
    for key in llm_config._ENV_CONFIG_KEYS:
        monkeypatch.delenv(key, raising=False)


def _write_llm_config(path, *, provider: str, model: str, base_url: str, api_key: str):
    path.write_text(
        json.dumps(
            {
                "provider": provider,
                "model": model,
                "base_url": base_url,
                "api_key": api_key,
                "temperature": 0.2,
                "max_output_tokens": 123,
            }
        ),
        encoding="utf-8",
    )


def test_load_llm_config_falls_back_to_env(monkeypatch, tmp_path):
    _clear_llm_env(monkeypatch)
    monkeypatch.setattr(llm_config, "_default_config_path", lambda: tmp_path / "missing.json")
    monkeypatch.setenv("TRACE_LLM_PROVIDER", "openai_chat_compat")
    monkeypatch.setenv("TRACE_LLM_MODEL", "env-chat-model")
    monkeypatch.setenv("TRACE_LLM_API_KEY", "env-key")
    monkeypatch.setenv("TRACE_LLM_BASE_URL", "https://compat.example/v1")
    monkeypatch.setenv("TRACE_LLM_TEMPERATURE", "0.2")
    monkeypatch.setenv("TRACE_LLM_MAX_OUTPUT_TOKENS", "123")

    config = llm_config.load_llm_config()

    assert config is not None
    assert config.provider == "openai_chat_compat"
    assert config.model == "env-chat-model"
    assert config.api_key == "env-key"
    assert config.base_url == "https://compat.example/v1"
    assert config.temperature == 0.2
    assert config.max_output_tokens == 123


def test_explicit_missing_llm_config_file_fails(monkeypatch, tmp_path):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("TRACE_LLM_CONFIG_FILE", str(tmp_path / "missing.json"))

    with pytest.raises(ValueError, match="配置文件不存在"):
        llm_config.load_llm_config()


def test_run_eval_list_models_prefers_config_api_key_over_stale_openai_env(monkeypatch, tmp_path, capsys):
    _clear_llm_env(monkeypatch)
    config = tmp_path / "llm.json"
    _write_llm_config(
        config,
        provider="openai_chat_compat",
        model="cfg-chat-model",
        base_url="https://cfg.example/v1",
        api_key="file-key",
    )
    monkeypatch.setenv("TRACE_LLM_CONFIG_FILE", str(config))
    monkeypatch.setenv("OPENAI_API_KEY", "stale-env-key")

    import app.agents.llm_factory as llm_factory
    from eval.harness import run_eval

    captured = {}

    class DummyLLM:
        def list_models(self):
            return ["cfg-chat-model"]

        def close(self):
            captured["closed"] = True

    def fake_create_llm(provider, model, **kwargs):
        captured["provider"] = provider
        captured["model"] = model
        captured.update(kwargs)
        return DummyLLM()

    monkeypatch.setattr(llm_factory, "create_llm", fake_create_llm)
    monkeypatch.setattr(sys, "argv", ["run_eval.py", "--list-models"])

    run_eval.main()

    assert capsys.readouterr().out.strip() == "cfg-chat-model"
    assert captured["provider"] == "openai_chat_compat"
    assert captured["model"] == "cfg-chat-model"
    assert captured["api_key"] == "file-key"
    assert captured["base_url"] == "https://cfg.example/v1"
    assert captured["closed"] is True


def test_llm_for_strategy_passes_frozen_temperature_to_client(monkeypatch):
    # 回归保护 P1#2：真实 client 必须收到冻结进 snapshot 的 temperature，
    # 而不是 model_params.get("temperature")（那里根本没有这个 key，会退回 None）。
    import app.services.test_runs as test_run_service
    from app.schemas.strategy import StrategyVersionSpec

    # 模拟从 snapshot 恢复后的 spec：temperature 在 spec 上，model_params 里没有 temperature。
    spec = StrategyVersionSpec(
        id="sv-x",
        name="x",
        workflow_type="direct",
        model_provider="openai",
        model_name="model-a",
        model_params={"base_url": "https://api.a.test/v1", "max_output_tokens": 256},
        temperature=0.2,
    )

    captured = {}

    def fake_create_llm(provider, model, **kwargs):
        captured["provider"] = provider
        captured["model"] = model
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(test_run_service, "create_llm", fake_create_llm)
    monkeypatch.setattr(test_run_service, "_api_key_for_provider", lambda provider: "key-x")

    test_run_service._llm_for_strategy(spec)

    # create_llm 收到的 temperature 必须等于冻结值（snapshot.resolved_llm.temperature 的来源）。
    assert captured["temperature"] == spec.temperature == 0.2


def test_execute_run_uses_frozen_strategy_snapshot(monkeypatch, tmp_path, clean_db):
    config_a = tmp_path / "llm-a.json"
    config_b = tmp_path / "llm-b.json"
    _write_llm_config(
        config_a,
        provider="openai",
        model="model-a",
        base_url="https://api.a.test/v1",
        api_key="key-a",
    )
    _write_llm_config(
        config_b,
        provider="openai",
        model="model-b",
        base_url="https://api.b.test/v1",
        api_key="key-b",
    )
    monkeypatch.setenv("TRACE_LLM_CONFIG_FILE", str(config_a))

    calls = []

    class DummyTask:
        def delay(self, run_id, budget_override):
            calls.append((run_id, budget_override))

    import app.services.test_runs as test_run_service
    import app.workers.tasks as task_module

    monkeypatch.setattr(task_module, "execute_run_task", DummyTask())

    app = create_app()
    with TestClient(app) as client:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        (project_root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

        project = client.post("/api/v1/projects", json={"name": "demo-project", "local_path": str(project_root)}).json()
        snapshot = client.post(f"/api/v1/projects/{project['id']}/snapshots", json={}).json()
        direct = client.get("/api/v1/strategy-versions/sv-direct-v1").json()
        plan = client.post(
            "/api/v1/test-plans",
            json={
                "project_id": project["id"],
                "name": "demo-plan",
                "target_scope": [],
                "goal": "测试 calc 模块",
                "budget": {"timeout_seconds": 60, "allow_reflection": False},
                "default_strategy_version_id": direct["id"],
            },
        ).json()

        run = client.post(f"/api/v1/test-plans/{plan['id']}/runs", json={"snapshot_id": snapshot["id"]}).json()

    assert calls and calls[0][0] == run["id"]
    assert run["strategy_snapshot"]["model_name"] == "model-a"
    assert run["strategy_snapshot"]["model_params"]["base_url"] == "https://api.a.test/v1"

    monkeypatch.setenv("TRACE_LLM_CONFIG_FILE", str(config_b))
    captured = {}

    class DummyLLM:
        def close(self):
            captured["closed"] = True

    def fake_llm_for_strategy(strategy_spec):
        captured["llm_spec"] = strategy_spec
        return DummyLLM()

    def fake_execute_run(**kwargs):
        captured["execute_spec"] = kwargs["strategy_spec"]
        run_record = kwargs["run"]
        run_record.status = "completed"
        kwargs["recorder"].save_run(run_record)

    monkeypatch.setattr(test_run_service, "_llm_for_strategy", fake_llm_for_strategy)
    monkeypatch.setattr(test_run_service, "execute_run", fake_execute_run)

    with Session(get_engine()) as session:
        completed = test_run_service.execute_run_sync(session, run_id=run["id"])

    assert captured["closed"] is True
    assert captured["llm_spec"].model_name == "model-a"
    assert captured["llm_spec"].model_params["base_url"] == "https://api.a.test/v1"
    assert captured["execute_spec"].model_name == "model-a"
    assert completed.status == "completed"
    assert completed.strategy_snapshot["model_name"] == "model-a"
    assert completed.strategy_snapshot["model_params"]["base_url"] == "https://api.a.test/v1"
