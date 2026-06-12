from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import get_engine
from app.main import create_app
from app.models import load_all_models


def _reset_db():
    engine = get_engine()
    load_all_models()
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        for table in [
            "test_reports",
            "run_artifacts",
            "trace_steps",
            "run_events",
            "pytest_case_results",
            "generated_test_cases",
            "generated_test_files",
            "run_attempts",
            "run_plan_items",
            "test_runs",
            "test_plans",
            "strategy_versions",
            "project_snapshots",
            "projects",
        ]:
            session.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
        session.commit()


def test_sync_run_via_api(tmp_path, monkeypatch):
    _reset_db()
    app = create_app()
    client = TestClient(app)

    project_root = tmp_path / "proj"
    project_root.mkdir()
    (project_root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    project = client.post(
        "/api/v1/projects",
        json={"name": "demo-project", "local_path": str(project_root)},
    ).json()
    snapshot = client.post(f"/api/v1/projects/{project['id']}/snapshots", json={}).json()
    strategies = client.get("/api/v1/strategy-versions").json()
    direct = next(x for x in strategies if x["id"] == "sv-direct-v1")
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
    assert run["status"] == "completed"
    assert run["strategy_version_id"] == direct["id"]

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
