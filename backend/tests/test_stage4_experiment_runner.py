from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.main import create_app
from app.models import ExperimentCleanRun, ExperimentReplayRun, RunArtifact, TestReplay as ReplayModel
from app.services.evaluation_seed import DEMO_DATASET_ID, seed_demo_dataset
from app.services.strategies import seed_strategy_versions
from eval.harness.run_eval import run_full_eval, run_full_eval_via_service


def _seed_v2_demo() -> None:
    with Session(get_engine()) as session:
        seed_strategy_versions(session)
        seed_demo_dataset(session)


def test_experiment_runner_creates_clean_runs_replays_and_db_metrics(tmp_path, clean_db):
    _seed_v2_demo()
    app = create_app()

    with TestClient(app) as client:
        create_response = client.post(
            "/api/v1/experiments",
            json={
                "id": "exp-stage4-demo",
                "name": "stage4 demo",
                "dataset_id": DEMO_DATASET_ID,
                "strategy_version_ids": ["sv-direct-v1", "sv-plan-v1", "sv-react-v1"],
                "repeat_count": 1,
                "llm_override": {"provider": "mock", "model": "mock-1"},
            },
        )
        assert create_response.status_code == 200
        assert create_response.json()["status"] == "draft"

        run_response = client.post("/api/v1/experiments/exp-stage4-demo/runs")
        assert run_response.status_code == 200, run_response.text
        experiment = run_response.json()
        assert experiment["status"] == "completed"

        metrics_response = client.get("/api/v1/experiments/exp-stage4-demo/metrics")
        assert metrics_response.status_code == 200, metrics_response.text
        metrics = metrics_response.json()

    rows = {row["strategy_id"]: row for row in metrics["rows"]}
    assert rows["direct"]["captured_per_repeat"] == [5]
    assert rows["direct"]["false_positive_rate"] == 1.0
    assert rows["direct"]["cost_per_captured_bug_status"] == "ok"
    assert rows["plan_execute"]["captured_per_repeat"] == [6]
    assert rows["plan_execute"]["false_positive_rate"] == 0.0
    assert rows["react_reflection"]["captured_per_repeat"] == [6]
    assert rows["react_reflection"]["reflection_used"] is True

    matrix = metrics["capture_matrix"]
    assert matrix["variant-wrong-status"]["direct"] is False
    assert matrix["variant-wrong-status"]["plan_execute"] is True
    assert matrix["variant-wrong-status"]["react_reflection"] is True
    assert metrics["data_source"]["kind"] == "mock"

    harness = run_full_eval(tmp_path / "harness", repeats=1)
    harness_rows = {row["strategy_id"]: row for row in harness["rows"]}
    assert rows["direct"]["captured_per_repeat"] == harness_rows["sv-direct-v1"]["captured_per_repeat"]
    assert rows["plan_execute"]["captured_per_repeat"] == harness_rows["sv-plan-v1"]["captured_per_repeat"]
    assert rows["react_reflection"]["captured_per_repeat"] == harness_rows["sv-react-v1"]["captured_per_repeat"]

    assert len(metrics["clean_runs"]) == 3
    assert len(metrics["experiment_replay_runs"]) == 18
    assert all(replay["llm_calls"] == 0 for replay in metrics["replay_runs"])
    assert any(replay["bug_variant_id"] is None for replay in metrics["replay_runs"])

    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(ExperimentCleanRun)) == 3
        assert session.scalar(select(func.count()).select_from(ExperimentReplayRun)) == 18
        assert session.scalar(select(func.count()).select_from(ReplayModel)) == 21

        artifacts = list(session.scalars(select(RunArtifact).where(RunArtifact.artifact_type == "generated_test_set")))
        assert len(artifacts) == 3
        for artifact in artifacts:
            data = Path(artifact.uri).read_bytes()
            assert hashlib.sha256(data).hexdigest() == artifact.content_hash
            payload = json.loads(data.decode("utf-8"))
            assert payload["files"]
            assert artifact.metadata_json["kind"] == "generated_test_set"
            assert artifact.metadata_json["experiment_id"] == "exp-stage4-demo"


def test_experiment_metrics_use_null_cost_when_no_bug_is_captured(clean_db):
    _seed_v2_demo()
    app = create_app()

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/experiments",
            json={
                "id": "exp-zero-capture",
                "name": "zero capture",
                "dataset_id": DEMO_DATASET_ID,
                "strategy_version_ids": ["sv-direct-v1"],
                "repeat_count": 1,
                "llm_override": {"provider": "mock", "model": "mock-1"},
            },
        )
        assert created.status_code == 200
        assert client.post("/api/v1/experiments/exp-zero-capture/runs").status_code == 200

    with Session(get_engine()) as session:
        for replay_result in session.scalars(select(ExperimentReplayRun)):
            replay_result.captured_bug = False
            replay_result.replay_metrics = {
                "capture_rule": "clean_passed_variant_assertion_failure_same_nodeid",
                "clean_passed_nodeids": [],
                "variant_assertion_failure_nodeids": [],
                "capturing_nodeids": [],
            }
        session.commit()

    with TestClient(app) as client:
        metrics = client.get("/api/v1/experiments/exp-zero-capture/metrics").json()
    [row] = metrics["rows"]
    assert row["captured_per_repeat"] == [0]
    assert row["cost_per_captured_bug"] is None
    assert row["cost_per_captured_bug_status"] == "no_bug_captured"


def test_eval_cli_service_path_reuses_experiment_service(clean_db):
    result = run_full_eval_via_service(repeats=1, llm_override={"provider": "mock", "model": "mock-1"})
    rows = {row["strategy_id"]: row for row in result["rows"]}

    assert rows["direct"]["captured_per_repeat"] == [5]
    assert rows["plan_execute"]["captured_per_repeat"] == [6]
    assert rows["react_reflection"]["captured_per_repeat"] == [6]
    assert "variant-wrong-status" in result["matrix_md"]
