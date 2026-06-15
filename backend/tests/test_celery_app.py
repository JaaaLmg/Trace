from fastapi.testclient import TestClient

from app.main import create_app
from app.workers.celery_app import celery_app
from app.workers.tasks import execute_run_task


def test_celery_registers_execute_run_task():
    assert execute_run_task.name == "trace.execute_run"
    assert "app.workers.tasks" in celery_app.conf.include
    assert celery_app.conf.task_default_queue == "trace_test_runs"


def test_worker_task_returns_persisted_failed_run(monkeypatch, tmp_path, clean_db):
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
                "goal": "test calc",
                "budget": {"timeout_seconds": 60, "allow_reflection": False},
                "default_strategy_version_id": direct["id"],
            },
        ).json()
        run = client.post(
            f"/api/v1/test-plans/{plan['id']}/runs",
            json={"snapshot_id": snapshot["id"]},
        ).json()
        run_id = run["id"]

    def fail_execute(*args, **kwargs):
        raise PermissionError("refused")

    monkeypatch.setattr(task_module, "execute_run_sync", fail_execute)

    assert execute_run_task.run(run_id, {}) == run_id
