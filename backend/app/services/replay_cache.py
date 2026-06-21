from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Experiment, ExperimentCleanRun, TestReplay
from app.services.artifact_cleanup import _safe_cleanup_path
from app.services.experiments import ExperimentNotFoundError


def list_replay_cache_entries(
    session: Session,
    *,
    experiment_id: str | None = None,
    dataset_id: str | None = None,
    runtime_profile_id: str | None = None,
    cache_status: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    if experiment_id and session.get(Experiment, experiment_id) is None:
        raise ExperimentNotFoundError("experiment not found")
    stmt = select(TestReplay, ExperimentCleanRun, Experiment).join(
        ExperimentCleanRun, ExperimentCleanRun.id == TestReplay.experiment_clean_run_id
    ).join(Experiment, Experiment.id == ExperimentCleanRun.experiment_id)
    if experiment_id:
        stmt = stmt.where(Experiment.id == experiment_id)
    if dataset_id:
        stmt = stmt.where(Experiment.dataset_id == dataset_id)
    if cache_status:
        stmt = stmt.where(TestReplay.cache_status == cache_status)
    stmt = stmt.order_by(TestReplay.created_at.desc(), TestReplay.id.asc()).limit(max(1, min(limit, 1000)))
    entries = []
    for replay, clean, experiment in session.execute(stmt):
        snapshot = replay.runtime_snapshot or {}
        if runtime_profile_id and snapshot.get("runtime_profile_id") != runtime_profile_id:
            continue
        manifest = replay.workspace_manifest or {}
        workspace_root = manifest.get("workspace_root")
        reused_from_replay_id = manifest.get("reused_from_replay_id")
        workspace_exists = Path(str(workspace_root)).exists() if workspace_root else False
        entries.append(
            {
                "replay_id": replay.id,
                "experiment_id": experiment.id,
                "dataset_id": experiment.dataset_id,
                "clean_run_id": clean.id,
                "bug_variant_id": replay.bug_variant_id,
                "runtime_profile_id": snapshot.get("runtime_profile_id"),
                "executor": snapshot.get("executor"),
                "cache_key": replay.cache_key,
                "cache_status": replay.cache_status,
                "source_replay_id": replay.source_replay_id,
                "reused_from_replay_id": reused_from_replay_id,
                "invalidation_reasons": (replay.executor_metadata or {}).get("cache_invalidation_reasons", []),
                "workspace_root": workspace_root,
                "workspace_exists": workspace_exists,
                "created_at": replay.created_at.isoformat() if replay.created_at else None,
            }
        )
    return entries


def cleanup_replay_cache_workspaces(
    session: Session,
    *,
    experiment_id: str,
    dry_run: bool = True,
    cache_statuses: list[str] | None = None,
) -> dict[str, Any]:
    statuses = set(cache_statuses or ["hit", "stale"])
    entries = list_replay_cache_entries(session, experiment_id=experiment_id, limit=1000)
    candidates = []
    for entry in entries:
        if entry["cache_status"] not in statuses or not entry.get("workspace_root"):
            continue
        if entry.get("reused_from_replay_id"):
            continue
        path = _safe_cleanup_path(Path(str(entry["workspace_root"])))
        candidates.append({**entry, "path": str(path), "exists": path.exists()})
    deleted = []
    if not dry_run:
        import shutil

        for candidate in candidates:
            path = Path(candidate["path"])
            if path.exists():
                shutil.rmtree(path)
                deleted.append(candidate)
    return {
        "experiment_id": experiment_id,
        "dry_run": dry_run,
        "cache_statuses": sorted(statuses),
        "candidate_count": len(candidates),
        "deleted_count": len(deleted),
        "candidates": candidates,
        "deleted": deleted,
    }
