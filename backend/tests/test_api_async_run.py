from fastapi.testclient import TestClient

from app.main import create_app
from app.workers.celery_app import celery_app


def test_async_run_is_enqueued(monkeypatch, tmp_path, clean_db):
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
            json={"snapshot_id": snapshot["id"], "budget_override": {"timeout_seconds": 30}},
        )
        assert response.status_code == 200
        run = response.json()
        assert run["status"] == "queued"
        assert run["strategy_snapshot"]["workflow_type"] == "direct"
        assert "prompts" in run["strategy_snapshot"]
        assert run["runtime_snapshot"]["executor"] == "local_subprocess"
        assert run["runtime_snapshot"]["budget_override"] == {"timeout_seconds": 30}
        assert calls and calls[0][0] == run["id"]

        events = client.get(f"/api/v1/test-runs/{run['id']}/events").json()
        assert any(e["event_type"] == "run_enqueued" for e in events)

        bad = client.post(
            f"/api/v1/test-plans/{plan['id']}/runs",
            json={"snapshot_id": snapshot["id"], "budget_override": {"timeout_secondz": 30}},
        )
        assert bad.status_code == 422


def test_async_run_executes_with_celery_eager(monkeypatch, tmp_path, clean_db):
    monkeypatch.setattr(celery_app.conf, "task_always_eager", True)
    monkeypatch.setattr(celery_app.conf, "task_eager_propagates", True)

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

        response = client.post(f"/api/v1/test-plans/{plan['id']}/runs", json={"snapshot_id": snapshot["id"]})
        assert response.status_code == 200
        run = response.json()
        assert run["status"] == "completed"

        events = client.get(f"/api/v1/test-runs/{run['id']}/events").json()
        assert any(e["event_type"] == "run_enqueued" for e in events)
        assert any(e["event_type"] == "run_finish" for e in events)

        report = client.get(f"/api/v1/test-runs/{run['id']}/report")
        assert report.status_code == 200
        assert report.json()["metrics"]["final_passed"] == 1
