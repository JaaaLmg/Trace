from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.agents.llm import MockLLM
from app.agents import prompts
from app.main import create_app
from app.services.test_runs import execute_run_sync
from app.db.session import get_engine
from sqlalchemy.orm import Session


def test_run_records_source_context_and_report_quality(monkeypatch, tmp_path, clean_db):
    class DummyTask:
        def delay(self, run_id, budget_override):
            return None

    import app.workers.tasks as task_module

    monkeypatch.setattr(task_module, "execute_run_task", DummyTask())
    monkeypatch.setenv("TRACE_LLM_CONFIG_FILE", "")

    def responder(messages):
        blob = "\n".join(m.content for m in messages)
        if "TASK: GENERATE" in blob:
            return json.dumps(
                {
                    "test_file_content": "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
                    "cases": [{"test_name": "test_add", "target_function": "add", "assertion_summary": "2+3=5"}],
                    "coverage_notes": "stage2 smoke",
                },
                ensure_ascii=False,
            )
        return json.dumps({"fixed_content": "", "fix_reason": "", "changed_points": []}, ensure_ascii=False)

    app = create_app()
    with TestClient(app) as client:
        project_root = tmp_path / "proj"
        project_root.mkdir(parents=True)
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

        run = client.post(
            f"/api/v1/test-plans/{plan['id']}/runs",
            json={"snapshot_id": snapshot["id"], "llm_provider": "mock", "llm_model": "mock-stage2"},
        ).json()

    with Session(get_engine()) as session:
        import app.services.test_runs as test_run_service

        monkeypatch.setattr(test_run_service, "_mock_llm", lambda: MockLLM(responder))
        completed = execute_run_sync(session, run_id=run["id"])
        assert completed.status == "completed"

    with TestClient(create_app()) as client:
        stored = client.get(f"/api/v1/test-runs/{run['id']}").json()
        assert stored["runtime_snapshot"]["runtime_profile_name"] == "Default Local Subprocess"
        assert stored["strategy_snapshot"]["resolved_llm"]["provider"]

        events = client.get(f"/api/v1/test-runs/{run['id']}/events").json()
        assert any(event["event_type"] == "run_enqueued" for event in events)

        report = client.get(f"/api/v1/test-runs/{run['id']}/report").json()
        assert report["metrics"]["report_quality"]["context_completeness"]["context_incomplete"] is False
        assert report["metrics"]["report_quality"]["test_inventory"]
        assert report["metrics"]["report_quality"]["assertion_summaries"]
