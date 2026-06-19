from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.main import create_app
from app.models.runtime_profile import RuntimeProfile
from app.models.versioning import PromptVersion, Strategy, ToolSchemaVersion


def test_stage1_seed_creates_versioning_records(clean_db):
    app = create_app()
    with Session(get_engine()) as session:
        strategies = list(session.scalars(select(Strategy).order_by(Strategy.id.asc())))
        prompt_versions = list(session.scalars(select(PromptVersion).order_by(PromptVersion.id.asc())))
        tool_schema_versions = list(session.scalars(select(ToolSchemaVersion).order_by(ToolSchemaVersion.id.asc())))

    assert {item.id for item in strategies} == {"direct", "plan_execute", "react_reflection"}
    assert {item.id for item in prompt_versions} == {"pv-direct_v1", "pv-plan_v1", "pv-react_v1"}
    assert {item.id for item in tool_schema_versions} == {"tsv-tools_v1"}


def test_create_run_binds_default_runtime_profile_and_freezes_full_snapshots(monkeypatch, tmp_path, clean_db):
    calls = []

    class DummyTask:
        def delay(self, run_id, budget_override):
            calls.append((run_id, budget_override))

    import app.workers.tasks as task_module

    monkeypatch.setattr(task_module, "execute_run_task", DummyTask())

    app = create_app()
    with TestClient(app) as client:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        (project_root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

        project = client.post("/api/v1/projects", json={"name": "demo-project", "local_path": str(project_root)}).json()
        runtime_profiles = client.get(f"/api/v1/projects/{project['id']}/runtime-profiles")
        assert runtime_profiles.status_code == 200
        [runtime_profile] = runtime_profiles.json()

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

        response = client.post(
            f"/api/v1/test-plans/{plan['id']}/runs",
            json={
                "snapshot_id": snapshot["id"],
                "runtime_profile_id": runtime_profile["id"],
                "budget_override": {"timeout_seconds": 45},
            },
        )
        assert response.status_code == 200
        run = response.json()

        assert run["runtime_profile_id"] == runtime_profile["id"]
        assert run["runtime_snapshot"]["runtime_profile_id"] == runtime_profile["id"]
        assert run["runtime_snapshot"]["runtime_profile_name"] == "Default Local Subprocess"
        assert run["runtime_snapshot"]["executor"] == "local_subprocess"
        assert run["runtime_snapshot"]["executor_capabilities"]["network_enforced"] is False
        assert run["runtime_snapshot"]["test_command"]
        assert "env_template" in run["runtime_snapshot"]
        assert run["strategy_snapshot"]["prompt_version_id"] == "pv-direct_v1"
        assert run["strategy_snapshot"]["tool_schema_version_id"] == "tsv-tools_v1"
        assert "prompt_content" in run["strategy_snapshot"]
        assert "tool_schema_json" in run["strategy_snapshot"]
        assert run["strategy_snapshot"]["resolved_llm"]["provider"]
        assert calls and calls[0][0] == run["id"]

        updated = client.patch(
            f"/api/v1/runtime-profiles/{runtime_profile['id']}",
            json={"name": "Changed After Run", "timeout_seconds": 9},
        )
        assert updated.status_code == 200
        frozen = client.get(f"/api/v1/test-runs/{run['id']}").json()
        assert frozen["runtime_snapshot"]["runtime_profile_name"] == "Default Local Subprocess"
        assert frozen["runtime_snapshot"]["timeout_seconds"] == 45


def test_runtime_profile_detail_route_returns_seeded_default(tmp_path, clean_db):
    app = create_app()
    with TestClient(app) as client:
        project_root = tmp_path / "proj"
        project_root.mkdir()

        project = client.post("/api/v1/projects", json={"name": "demo-project", "local_path": str(project_root)}).json()
        response = client.get(f"/api/v1/projects/{project['id']}/runtime-profiles")
        assert response.status_code == 200
        [profile] = response.json()

        detail = client.get(f"/api/v1/runtime-profiles/{profile['id']}")
        assert detail.status_code == 200
        assert detail.json()["project_id"] == project["id"]

        with Session(get_engine()) as session:
            stored = session.get(RuntimeProfile, profile["id"])
        assert stored is not None


def test_runtime_profile_rejects_unsupported_local_policy(tmp_path, clean_db):
    app = create_app()
    with TestClient(app) as client:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        project = client.post("/api/v1/projects", json={"name": "demo-project", "local_path": str(project_root)}).json()
        response = client.post(
            f"/api/v1/projects/{project['id']}/runtime-profiles",
            json={
                "name": "bad local",
                "executor": "local_subprocess",
                "network_policy": "disabled",
            },
        )
        assert response.status_code == 400
        assert "cannot enforce" in response.json()["detail"]


def test_runtime_profile_accepts_docker_profile_with_image(tmp_path, clean_db):
    app = create_app()
    with TestClient(app) as client:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        project = client.post("/api/v1/projects", json={"name": "demo-project", "local_path": str(project_root)}).json()
        response = client.post(
            f"/api/v1/projects/{project['id']}/runtime-profiles",
            json={
                "name": "docker",
                "executor": "docker",
                "image": "python:3.12-slim",
                "network_policy": "disabled",
                "timeout_seconds": 30,
            },
        )
        assert response.status_code == 200, response.text
        profile = response.json()
        assert profile["executor"] == "docker"
        assert profile["image"] == "python:3.12-slim"
        assert profile["resource_limits"]["timeout_seconds"] == 30


def test_runtime_profile_rejects_secret_env_key(tmp_path, clean_db):
    app = create_app()
    with TestClient(app) as client:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        project = client.post("/api/v1/projects", json={"name": "demo-project", "local_path": str(project_root)}).json()
        response = client.post(
            f"/api/v1/projects/{project['id']}/runtime-profiles",
            json={
                "name": "secret-env",
                "env_template": {"API_TOKEN": "x"},
            },
        )
        assert response.status_code == 400
        assert "secret" in response.json()["detail"]


def test_runtime_profile_update_and_archive_routes(tmp_path, clean_db):
    app = create_app()
    with TestClient(app) as client:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        project = client.post("/api/v1/projects", json={"name": "demo-project", "local_path": str(project_root)}).json()
        [profile] = client.get(f"/api/v1/projects/{project['id']}/runtime-profiles").json()

        updated = client.patch(
            f"/api/v1/runtime-profiles/{profile['id']}",
            json={"name": "renamed", "timeout_seconds": 33},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["name"] == "renamed"
        assert updated.json()["resource_limits"]["timeout_seconds"] == 33

        archived = client.post(f"/api/v1/runtime-profiles/{profile['id']}/archive")
        assert archived.status_code == 200
        assert archived.json()["archived_at"] is not None

        blocked = client.patch(f"/api/v1/runtime-profiles/{profile['id']}", json={"name": "blocked"})
        assert blocked.status_code == 400

        [next_default] = client.get(f"/api/v1/projects/{project['id']}/runtime-profiles").json()
        assert next_default["id"] != profile["id"]
        assert next_default["archived_at"] is None


def test_create_run_accepts_llm_override_and_freezes_selected_model(monkeypatch, tmp_path, clean_db):
    class DummyTask:
        def delay(self, run_id, budget_override):
            return None

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

        response = client.post(
            f"/api/v1/test-plans/{plan['id']}/runs",
            json={
                "snapshot_id": snapshot["id"],
                "llm_provider": "mock",
                "llm_model": "mock-stage2",
                "llm_temperature": 0.15,
                "llm_max_output_tokens": 256,
            },
        )
        assert response.status_code == 200
        run = response.json()

        assert run["strategy_snapshot"]["resolved_llm"]["provider"] == "mock"
        assert run["strategy_snapshot"]["resolved_llm"]["model"] == "mock-stage2"
        assert run["strategy_snapshot"]["resolved_llm"]["temperature"] == 0.15
        assert run["strategy_snapshot"]["resolved_llm"]["max_output_tokens"] == 256
