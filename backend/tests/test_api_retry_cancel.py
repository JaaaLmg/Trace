from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.main import create_app
from app.services.test_runs import execute_run_sync


def _bootstrap(client: TestClient, root: Path):
    root.mkdir(parents=True, exist_ok=True)
    (root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    project = client.post("/api/v1/projects", json={"name": "demo-project", "local_path": str(root)}).json()
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
    return project, snapshot, direct, plan


def test_cancel_and_retry_enqueue(monkeypatch, tmp_path, clean_db):
    calls = []

    class DummyTask:
        def delay(self, run_id, budget_override):
            calls.append((run_id, budget_override))

    import app.workers.tasks as task_module

    monkeypatch.setattr(task_module, "execute_run_task", DummyTask())

    app = create_app()
    client = TestClient(app)
    _, snapshot, _, plan = _bootstrap(client, tmp_path / "proj")

    run = client.post(
        f"/api/v1/test-plans/{plan['id']}/runs",
        json={"snapshot_id": snapshot["id"], "budget_override": {"allow_reflection": True}},
    ).json()
    assert run["status"] == "queued"
    assert calls[0][1] == {"allow_reflection": True}

    cancelled = client.post(f"/api/v1/test-runs/{run['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    with Session(get_engine()) as session:
        still_cancelled = execute_run_sync(session, run_id=run["id"])
        assert still_cancelled.status == "cancelled"

    retried = client.post(f"/api/v1/test-runs/{run['id']}/retry")
    assert retried.status_code == 200
    retry_run = retried.json()
    assert retry_run["retry_of_run_id"] == run["id"]
    assert retry_run["status"] == "queued"
    assert len(calls) >= 2
    assert calls[-1][1] == {"allow_reflection": True}
