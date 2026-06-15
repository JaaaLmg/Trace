from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.main import create_app
from app.services.test_runs import execute_run_sync


def test_sync_run_via_api(tmp_path, monkeypatch, clean_db):
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

        project = client.post(
            "/api/v1/projects",
            json={"name": "demo-project", "local_path": str(project_root)},
        ).json()
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

        run_resp = client.post(
            f"/api/v1/test-plans/{plan['id']}/runs",
            json={"snapshot_id": snapshot["id"]},
        )
        assert run_resp.status_code == 200, run_resp.text
        run = run_resp.json()
        assert run["status"] == "queued"
        assert run["strategy_version_id"] == direct["id"]
        assert calls and calls[0][0] == run["id"]

        with Session(get_engine()) as session:
            completed = execute_run_sync(session, run_id=run["id"])
            assert completed.status == "completed"

        events = client.get(f"/api/v1/test-runs/{run['id']}/events")
        assert events.status_code == 200
        assert any(e["event_type"] == "run_finish" for e in events.json())

        steps = client.get(f"/api/v1/test-runs/{run['id']}/trace-steps")
        assert steps.status_code == 200
        assert any(s["tool_name"] == "run_pytest" for s in steps.json())

        attempts = client.get(f"/api/v1/test-runs/{run['id']}/attempts")
        assert attempts.status_code == 200
        assert len(attempts.json()) >= 1

        pytest_results = client.get(f"/api/v1/test-runs/{run['id']}/pytest-results")
        assert pytest_results.status_code == 200
        assert any(r["status"] == "passed" for r in pytest_results.json())

        report = client.get(f"/api/v1/test-runs/{run['id']}/report")
        assert report.status_code == 200
        metrics = report.json()["metrics"]
        assert "strategy_version_id" in metrics
