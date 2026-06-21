from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

import app.models as models
from app.db.session import get_engine
from app.services.artifact_cleanup import (
    CleanupError,
    _safe_cleanup_path,
    cleanup_experiment_workspaces,
    experiment_artifact_inventory,
)
from app.services.replay_cache import cleanup_replay_cache_workspaces, list_replay_cache_entries
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


def test_artifact_inventory_and_replay_cache_listing(clean_db, cleanup_work_root: Path):
    completed = cleanup_work_root / "cache-completed"
    completed.mkdir()
    with Session(get_engine()) as session:
        experiment_id = _seed_cleanup_replays(
            session,
            experiment_id="exp-cache-inventory",
            replays=[("replay-source", "completed", completed), ("replay-cache-hit", "completed", completed)],
        )
        replay = session.get(models.TestReplay, "replay-cache-hit")
        assert replay is not None
        replay.cache_status = "hit"
        replay.cache_key = "cache-key-1"
        replay.runtime_snapshot = {"runtime_profile_id": "profile-1", "executor": "local_subprocess"}
        replay.source_replay_id = "replay-source"
        replay.workspace_manifest = {**dict(replay.workspace_manifest or {}), "reused_from_replay_id": "replay-source"}
        session.commit()

        inventory = experiment_artifact_inventory(session, experiment_id=experiment_id)
        entries = list_replay_cache_entries(session, experiment_id=experiment_id)
        cleanup = cleanup_replay_cache_workspaces(session, experiment_id=experiment_id, dry_run=True)

    assert inventory["artifact_count"] == 1
    assert inventory["workspace_count"] == 2
    assert entries[0]["cache_status"] == "hit"
    assert entries[0]["runtime_profile_id"] == "profile-1"
    assert entries[0]["reused_from_replay_id"] == "replay-source"
    assert cleanup["candidate_count"] == 0


def test_replay_cache_cleanup_skips_reused_source_workspace(clean_db, cleanup_work_root: Path):
    source_workspace = cleanup_work_root / "cache-source"
    stale_workspace = cleanup_work_root / "cache-stale"
    source_workspace.mkdir()
    stale_workspace.mkdir()
    (source_workspace / "evidence.txt").write_text("keep source evidence", encoding="utf-8")
    (stale_workspace / "tmp.txt").write_text("delete stale cache", encoding="utf-8")

    with Session(get_engine()) as session:
        experiment_id = _seed_cleanup_replays(
            session,
            experiment_id="exp-cache-cleanup-reuse",
            replays=[
                ("replay-source", "completed", source_workspace),
                ("replay-hit-alias", "completed", source_workspace),
                ("replay-stale", "completed", stale_workspace),
            ],
        )
        hit = session.get(models.TestReplay, "replay-hit-alias")
        stale = session.get(models.TestReplay, "replay-stale")
        assert hit is not None
        assert stale is not None
        hit.cache_status = "hit"
        hit.source_replay_id = "replay-source"
        hit.workspace_manifest = {
            **dict(hit.workspace_manifest or {}),
            "reused_from_replay_id": "replay-source",
        }
        stale.cache_status = "stale"
        session.commit()

        dry_run = cleanup_replay_cache_workspaces(session, experiment_id=experiment_id, dry_run=True)
        deleted = cleanup_replay_cache_workspaces(session, experiment_id=experiment_id, dry_run=False)

    assert dry_run["candidate_count"] == 1
    assert dry_run["candidates"][0]["replay_id"] == "replay-stale"
    assert deleted["deleted_count"] == 1
    assert source_workspace.exists()
    assert not stale_workspace.exists()


def test_workspace_cleanup_skips_reused_source_workspace(clean_db, cleanup_work_root: Path):
    source_workspace = cleanup_work_root / "workspace-source"
    source_workspace.mkdir()
    (source_workspace / "evidence.txt").write_text("keep source evidence", encoding="utf-8")

    with Session(get_engine()) as session:
        experiment_id = _seed_cleanup_replays(
            session,
            experiment_id="exp-workspace-cleanup-reuse",
            replays=[
                ("replay-source", "completed", source_workspace),
                ("replay-hit-alias", "completed", source_workspace),
            ],
        )
        hit = session.get(models.TestReplay, "replay-hit-alias")
        assert hit is not None
        hit.cache_status = "hit"
        hit.source_replay_id = "replay-source"
        hit.workspace_manifest = {
            **dict(hit.workspace_manifest or {}),
            "reused_from_replay_id": "replay-source",
        }
        session.commit()

        result = cleanup_experiment_workspaces(session, experiment_id=experiment_id, dry_run=False, keep_failed=True)

    assert result["candidate_count"] == 1
    assert result["deleted"][0]["replay_id"] == "replay-source"
    assert not source_workspace.exists()


def test_artifact_inventory_marks_unsafe_legacy_workspace(clean_db, cleanup_work_root: Path, tmp_path: Path):
    safe_workspace = cleanup_work_root / "safe-inventory"
    safe_workspace.mkdir()
    outside = tmp_path / "legacy-outside"
    outside.mkdir()

    with Session(get_engine()) as session:
        experiment_id = _seed_cleanup_replays(
            session,
            experiment_id="exp-inventory-unsafe",
            replays=[
                ("replay-safe", "completed", safe_workspace),
                ("replay-unsafe", "completed", outside),
            ],
        )
        inventory = experiment_artifact_inventory(session, experiment_id=experiment_id)

    unsafe = [item for item in inventory["workspaces"] if item["replay_id"] == "replay-unsafe"]
    assert unsafe
    assert unsafe[0]["safe"] is False
    assert "outside experiment work root" in unsafe[0]["error"]
    assert inventory["workspace_count"] == 2

