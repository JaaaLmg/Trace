from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

import app.models as models
from app.db.session import get_engine
from app.services.artifact_cleanup import CleanupError, _safe_cleanup_path, cleanup_experiment_workspaces
from app.services.evaluation_seed import DEMO_DATASET_ID, DEMO_SNAPSHOT_ID, seed_demo_dataset
from app.services.experiments import EXPERIMENT_WORK_ROOT
from app.services.strategies import seed_strategy_versions


@pytest.fixture
def cleanup_work_root():
    root = EXPERIMENT_WORK_ROOT / "cleanup-flow-tests"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        if root.exists():
            shutil.rmtree(root)


def _seed_cleanup_replays(
    session: Session,
    *,
    experiment_id: str,
    replays: list[tuple[str, str, Path | None]],
) -> str:
    seed_strategy_versions(session)
    seed_demo_dataset(session)
    snapshot = session.get(models.ProjectSnapshot, DEMO_SNAPSHOT_ID)
    assert snapshot is not None

    experiment = models.Experiment(
        id=experiment_id,
        name=experiment_id,
        dataset_id=DEMO_DATASET_ID,
        repeat_count=1,
        llm_override={"provider": "mock", "model": "mock-1"},
        status="completed",
    )
    plan = models.TestPlan(
        id="cleanup-plan",
        project_id=snapshot.project_id,
        name="cleanup plan",
        target_scope=[],
        goal="cleanup",
        budget={},
        output_options={},
        default_strategy_version_id="sv-direct-v1",
    )
    run = models.TestRun(
        id="cleanup-run",
        test_plan_id="cleanup-plan",
        project_snapshot_id=snapshot.id,
        strategy_version_id="sv-direct-v1",
        runtime_snapshot={},
        strategy_snapshot={},
        status="completed",
        pytest_summary={},
    )
    artifact = models.RunArtifact(
        id="cleanup-artifact",
        run_id="cleanup-run",
        artifact_type="generated_test_set",
        uri="memory://cleanup",
        content_hash="sha256:cleanup",
        size_bytes=1,
        metadata_json={},
    )
    clean = models.ExperimentCleanRun(
        id="cleanup-clean",
        experiment_id=experiment_id,
        eval_task_id="task-demo-shop-pricing-v2",
        strategy_version_id="sv-direct-v1",
        repeat_index=0,
        clean_run_id="cleanup-run",
        generated_test_set_artifact_id="cleanup-artifact",
        false_positive=False,
        clean_metrics={},
    )
    session.add_all([experiment, plan, run])
    session.commit()
    session.add(artifact)
    session.commit()
    session.add(clean)
    session.commit()

    for replay_id, status, workspace_root in replays:
        manifest = {"workspace_root": str(workspace_root)} if workspace_root is not None else {}
        session.add(
            models.TestReplay(
                id=replay_id,
                experiment_clean_run_id="cleanup-clean",
                generated_test_set_artifact_id="cleanup-artifact",
                target_snapshot_id=snapshot.id,
                bug_variant_id=None,
                status=status,
                pytest_summary={},
                runtime_snapshot={},
                executor_metadata={},
                workspace_manifest=manifest,
                cache_status="miss",
            )
        )
    session.commit()
    return experiment.id


def test_cleanup_rejects_experiment_work_root():
    with pytest.raises(CleanupError):
        _safe_cleanup_path(EXPERIMENT_WORK_ROOT)


def test_cleanup_rejects_path_outside_experiment_root(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(CleanupError):
        _safe_cleanup_path(outside)


def test_cleanup_accepts_child_path():
    child = EXPERIMENT_WORK_ROOT / "exp-safe" / "run"
    assert _safe_cleanup_path(child) == child.resolve()


def test_cleanup_workspaces_dry_run_collects_safe_completed_candidates(clean_db, cleanup_work_root: Path):
    completed = cleanup_work_root / "completed"
    failed = cleanup_work_root / "failed"
    missing = cleanup_work_root / "missing"
    completed.mkdir()
    failed.mkdir()

    with Session(get_engine()) as session:
        experiment_id = _seed_cleanup_replays(
            session,
            experiment_id="exp-cleanup-dry-run",
            replays=[
                ("replay-completed", "completed", completed),
                ("replay-failed", "failed", failed),
                ("replay-missing", "completed", missing),
                ("replay-no-workspace", "completed", None),
            ],
        )
        result = cleanup_experiment_workspaces(session, experiment_id=experiment_id, dry_run=True, keep_failed=True)

    assert result["dry_run"] is True
    assert result["keep_failed"] is True
    assert result["candidate_count"] == 2
    assert result["deleted_count"] == 0
    assert [(item["replay_id"], item["exists"]) for item in result["candidates"]] == [
        ("replay-completed", True),
        ("replay-missing", False),
    ]
    assert completed.exists()
    assert failed.exists()


def test_cleanup_workspaces_deletes_completed_candidates_only_when_keeping_failed(clean_db, cleanup_work_root: Path):
    completed = cleanup_work_root / "completed-delete"
    failed = cleanup_work_root / "failed-keep"
    completed.mkdir()
    failed.mkdir()

    with Session(get_engine()) as session:
        experiment_id = _seed_cleanup_replays(
            session,
            experiment_id="exp-cleanup-delete-completed",
            replays=[
                ("replay-completed", "completed", completed),
                ("replay-failed", "failed", failed),
            ],
        )
        result = cleanup_experiment_workspaces(session, experiment_id=experiment_id, dry_run=False, keep_failed=True)

    assert result["candidate_count"] == 1
    assert result["deleted_count"] == 1
    assert result["deleted"][0]["replay_id"] == "replay-completed"
    assert not completed.exists()
    assert failed.exists()


def test_cleanup_workspaces_can_include_failed_candidates_when_requested(clean_db, cleanup_work_root: Path):
    completed = cleanup_work_root / "completed-delete-all"
    failed = cleanup_work_root / "failed-delete-all"
    completed.mkdir()
    failed.mkdir()

    with Session(get_engine()) as session:
        experiment_id = _seed_cleanup_replays(
            session,
            experiment_id="exp-cleanup-delete-all",
            replays=[
                ("replay-completed", "completed", completed),
                ("replay-failed", "failed", failed),
            ],
        )
        result = cleanup_experiment_workspaces(session, experiment_id=experiment_id, dry_run=False, keep_failed=False)

    assert result["candidate_count"] == 2
    assert result["deleted_count"] == 2
    assert {item["replay_id"] for item in result["deleted"]} == {"replay-completed", "replay-failed"}
    assert not completed.exists()
    assert not failed.exists()

