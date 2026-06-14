from fastapi.testclient import TestClient
from pathlib import Path

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

        pending_report = client.get(f"/api/v1/test-runs/{run['id']}/report")
        assert pending_report.status_code == 200
        assert pending_report.json() is None

        missing_report = client.get("/api/v1/test-runs/does-not-exist/report")
        assert missing_report.status_code == 404

        bad = client.post(
            f"/api/v1/test-plans/{plan['id']}/runs",
            json={"snapshot_id": snapshot["id"], "budget_override": {"timeout_secondz": 30}},
        )
        assert bad.status_code == 422


def test_list_projects_hides_pytest_tmp_projects(tmp_path, clean_db):
    trace_root = Path(__file__).resolve().parents[2]
    app = create_app()
    with TestClient(app) as client:
        real_root = trace_root / "backend" / "tests" / "fixtures" / "async_demo_project"
        tmp_root = trace_root / ".pytest_tmp" / "test_sync_run_via_api0" / "proj"
        tmp_root.mkdir(parents=True)

        real_project = client.post(
            "/api/v1/projects",
            json={"name": "real-project", "local_path": str(real_root)},
        ).json()
        hidden_project = client.post(
            "/api/v1/projects",
            json={"name": "pytest-temp-project", "local_path": str(tmp_root)},
        ).json()

        projects = client.get("/api/v1/projects")
        assert projects.status_code == 200
        ids = {project["id"] for project in projects.json()}
        assert real_project["id"] in ids
        assert hidden_project["id"] not in ids


def test_list_projects_skips_inaccessible_legacy_paths(monkeypatch, tmp_path, clean_db):
    app = create_app()
    with TestClient(app) as client:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        project = client.post(
            "/api/v1/projects",
            json={"name": "demo-project", "local_path": str(project_root)},
        ).json()

        import app.services.path_policy as path_policy

        original_validate = path_policy.validate_project_root

        def deny_selected(path):
            if str(path) == project["local_path"]:
                raise ValueError("project path is not accessible: denied")
            return original_validate(path)

        monkeypatch.setattr(path_policy, "validate_project_root", deny_selected)

        projects = client.get("/api/v1/projects")
        assert projects.status_code == 200
        assert projects.json() == []


def test_project_and_snapshot_path_validation(tmp_path, clean_db):
    app = create_app()
    with TestClient(app) as client:
        missing = client.post(
            "/api/v1/projects",
            json={"name": "missing", "local_path": str(tmp_path / "missing")},
        )
        assert missing.status_code == 400

        project_root = tmp_path / "proj"
        project_root.mkdir()
        project = client.post(
            "/api/v1/projects",
            json={"name": "demo-project", "local_path": str(project_root)},
        )
        assert project.status_code == 200

        outside_root = tmp_path / "outside"
        outside_root.mkdir()
        snapshot = client.post(
            f"/api/v1/projects/{project.json()['id']}/snapshots",
            json={"root_path": str(outside_root)},
        )
        assert snapshot.status_code == 400
        assert "snapshot root must be inside project path" in snapshot.text


def test_run_rejects_snapshot_from_another_project(monkeypatch, tmp_path, clean_db):
    class DummyTask:
        def delay(self, run_id, budget_override):
            return None

    import app.workers.tasks as task_module

    monkeypatch.setattr(task_module, "execute_run_task", DummyTask())

    app = create_app()
    with TestClient(app) as client:
        root_a = tmp_path / "proj_a"
        root_b = tmp_path / "proj_b"
        root_a.mkdir()
        root_b.mkdir()
        project_a = client.post("/api/v1/projects", json={"name": "project-a", "local_path": str(root_a)}).json()
        project_b = client.post("/api/v1/projects", json={"name": "project-b", "local_path": str(root_b)}).json()
        snapshot_b = client.post(f"/api/v1/projects/{project_b['id']}/snapshots", json={}).json()
        direct = client.get("/api/v1/strategy-versions/sv-direct-v1").json()
        plan_a = client.post(
            "/api/v1/test-plans",
            json={
                "project_id": project_a["id"],
                "name": "plan-a",
                "target_scope": [],
                "goal": "test project a",
                "budget": {"timeout_seconds": 60, "allow_reflection": False},
                "default_strategy_version_id": direct["id"],
            },
        ).json()

        run = client.post(
            f"/api/v1/test-plans/{plan_a['id']}/runs",
            json={"snapshot_id": snapshot_b["id"]},
        )
        assert run.status_code == 400
        assert "snapshot does not belong" in run.text


def test_project_management_lists_snapshots_plans_and_runs(monkeypatch, tmp_path, clean_db):
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
        project = client.post(
            "/api/v1/projects",
            json={"name": "managed-project", "local_path": str(project_root)},
        ).json()
        snapshot = client.post(f"/api/v1/projects/{project['id']}/snapshots", json={}).json()
        direct = client.get("/api/v1/strategy-versions/sv-direct-v1").json()
        plan = client.post(
            "/api/v1/test-plans",
            json={
                "project_id": project["id"],
                "name": "managed-plan",
                "target_scope": ["."],
                "goal": "test managed project",
                "budget": {"timeout_seconds": 60, "allow_reflection": False},
                "default_strategy_version_id": direct["id"],
            },
        ).json()
        run = client.post(
            f"/api/v1/test-plans/{plan['id']}/runs",
            json={"snapshot_id": snapshot["id"]},
        ).json()

        snapshots = client.get(f"/api/v1/projects/{project['id']}/snapshots")
        assert snapshots.status_code == 200
        assert [item["id"] for item in snapshots.json()] == [snapshot["id"]]

        plans = client.get(f"/api/v1/projects/{project['id']}/test-plans")
        assert plans.status_code == 200
        assert [item["id"] for item in plans.json()] == [plan["id"]]

        project_runs = client.get(f"/api/v1/projects/{project['id']}/test-runs")
        assert project_runs.status_code == 200
        assert [item["id"] for item in project_runs.json()] == [run["id"]]

        plan_runs = client.get(f"/api/v1/test-plans/{plan['id']}/runs")
        assert plan_runs.status_code == 200
        assert [item["id"] for item in plan_runs.json()] == [run["id"]]


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
