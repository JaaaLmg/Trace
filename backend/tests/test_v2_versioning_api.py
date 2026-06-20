from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_create_runtime_profile_and_list_includes_it(tmp_path, clean_db):
    app = create_app()
    with TestClient(app) as client:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        project = client.post("/api/v1/projects", json={"name": "demo", "local_path": str(project_root)}).json()

        created = client.post(
            f"/api/v1/projects/{project['id']}/runtime-profiles",
            json={"name": "custom", "test_command": "python -m pytest -q -k pricing"},
        )
        assert created.status_code == 200
        profile = created.json()
        assert profile["network_policy"] == "default"
        assert profile["test_command"] == "python -m pytest -q -k pricing"

        listed = client.get(f"/api/v1/projects/{project['id']}/runtime-profiles").json()
        assert profile["id"] in {p["id"] for p in listed}


def test_create_runtime_profile_rejects_bad_network_policy(tmp_path, clean_db):
    app = create_app()
    with TestClient(app) as client:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        project = client.post("/api/v1/projects", json={"name": "demo", "local_path": str(project_root)}).json()

        bad = client.post(
            f"/api/v1/projects/{project['id']}/runtime-profiles",
            json={"name": "x", "network_policy": "wide-open"},
        )
        assert bad.status_code == 400


def test_create_prompt_tool_strategy_and_version_chain(tmp_path, clean_db):
    app = create_app()
    with TestClient(app) as client:
        prompt = client.post(
            "/api/v1/prompt-versions",
            json={"name": "p", "version": "v2", "content": {"system": "hi"}},
        ).json()
        assert prompt["content_hash"]

        tool = client.post(
            "/api/v1/tool-schema-versions",
            json={"version": "v2", "schema_payload": {"tools": ["analyze_project"]}},
        ).json()
        assert tool["content_hash"]
        assert tool["schema_payload"] == {"tools": ["analyze_project"]}

        strategy = client.post(
            "/api/v1/strategies",
            json={"name": "Custom Direct", "workflow_type": "direct"},
        ).json()

        version = client.post(
            f"/api/v1/strategies/{strategy['id']}/versions",
            json={
                "name": "Custom Direct v2",
                "version": "v2",
                "prompt_version_id": prompt["id"],
                "tool_schema_version_id": tool["id"],
                "temperature": 0.2,
            },
        )
        assert version.status_code == 200
        body = version.json()
        assert body["strategy_id"] == strategy["id"]
        assert body["prompt_version_id"] == prompt["id"]
        assert body["tool_schema_version_id"] == tool["id"]
        assert body["workflow_type"] == "direct"

        versions = client.get(f"/api/v1/strategies/{strategy['id']}/versions").json()
        assert body["id"] in {v["id"] for v in versions}


def test_create_strategy_version_requires_existing_prompt_and_tool(tmp_path, clean_db):
    app = create_app()
    with TestClient(app) as client:
        strategy = client.post(
            "/api/v1/strategies",
            json={"name": "Custom", "workflow_type": "direct"},
        ).json()

        bad = client.post(
            f"/api/v1/strategies/{strategy['id']}/versions",
            json={
                "name": "v",
                "version": "v2",
                "prompt_version_id": "pv-missing",
                "tool_schema_version_id": "tsv-missing",
            },
        )
        assert bad.status_code == 400
        assert "prompt version not found" in bad.text


def test_create_strategy_rejects_bad_workflow_type(clean_db):
    app = create_app()
    with TestClient(app) as client:
        bad = client.post("/api/v1/strategies", json={"name": "x", "workflow_type": "nonsense"})
        assert bad.status_code == 400
