from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Experiment, ExperimentCleanRun, RunArtifact, TestReplay
from app.services.experiments import EXPERIMENT_WORK_ROOT


class CleanupError(ValueError):
    pass


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _safe_cleanup_path(path: Path) -> Path:
    root = EXPERIMENT_WORK_ROOT.resolve()
    resolved = path.resolve()
    if resolved == root or not _is_relative_to(resolved, root):
        raise CleanupError(f"refusing to clean path outside experiment work root: {resolved}")
    return resolved


def cleanup_experiment_workspaces(
    session: Session,
    *,
    experiment_id: str,
    dry_run: bool = True,
    keep_failed: bool = True,
) -> dict:
    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        raise CleanupError("experiment not found")
    replay_rows = list(
        session.scalars(
            select(TestReplay)
            .join_from(TestReplay, ExperimentCleanRun)
            .where(ExperimentCleanRun.experiment_id == experiment_id)
            .order_by(TestReplay.created_at.asc(), TestReplay.id.asc())
        )
    )

    candidates = []
    for replay in replay_rows:
        if keep_failed and replay.status != "completed":
            continue
        manifest = replay.workspace_manifest or {}
        if manifest.get("reused_from_replay_id"):
            continue
        workspace_root = manifest.get("workspace_root")
        if not workspace_root:
            continue
        path = _safe_cleanup_path(Path(str(workspace_root)))
        candidates.append(
            {
                "replay_id": replay.id,
                "path": str(path),
                "status": replay.status,
                "exists": path.exists(),
            }
        )

    deleted = []
    if not dry_run:
        for candidate in candidates:
            path = Path(candidate["path"])
            if path.exists():
                shutil.rmtree(path)
                deleted.append(candidate)

    return {
        "experiment_id": experiment_id,
        "dry_run": dry_run,
        "keep_failed": keep_failed,
        "candidate_count": len(candidates),
        "deleted_count": len(deleted),
        "candidates": candidates,
        "deleted": deleted,
    }


def experiment_artifact_inventory(session: Session, *, experiment_id: str) -> dict:
    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        raise CleanupError("experiment not found")
    clean_runs = list(
        session.scalars(
            select(ExperimentCleanRun)
            .where(ExperimentCleanRun.experiment_id == experiment_id)
            .order_by(ExperimentCleanRun.created_at.asc(), ExperimentCleanRun.id.asc())
        )
    )
    replays = list(
        session.scalars(
            select(TestReplay)
            .join_from(TestReplay, ExperimentCleanRun)
            .where(ExperimentCleanRun.experiment_id == experiment_id)
            .order_by(TestReplay.created_at.asc(), TestReplay.id.asc())
        )
    )
    artifact_ids = {clean.generated_test_set_artifact_id for clean in clean_runs if clean.generated_test_set_artifact_id}
    artifact_ids.update(replay.generated_test_set_artifact_id for replay in replays if replay.generated_test_set_artifact_id)
    artifacts = []
    if artifact_ids:
        artifacts = list(
            session.scalars(
                select(RunArtifact)
                .where(RunArtifact.id.in_(artifact_ids))
                .order_by(RunArtifact.created_at.asc(), RunArtifact.id.asc())
            )
        )
    workspace_bytes = 0
    workspaces = []
    for replay in replays:
        workspace_root = (replay.workspace_manifest or {}).get("workspace_root")
        if not workspace_root:
            continue
        try:
            path = _safe_cleanup_path(Path(str(workspace_root)))
        except CleanupError as exc:
            workspaces.append(
                {
                    "replay_id": replay.id,
                    "path": str(workspace_root),
                    "exists": None,
                    "size_bytes": 0,
                    "safe": False,
                    "error": str(exc),
                }
            )
            continue
        size = 0
        if path.exists():
            size = sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
            workspace_bytes += size
        workspaces.append(
            {
                "replay_id": replay.id,
                "path": str(path),
                "exists": path.exists(),
                "size_bytes": size,
                "safe": True,
            }
        )
    artifact_bytes = sum(int(artifact.size_bytes or 0) for artifact in artifacts)
    return {
        "experiment_id": experiment_id,
        "artifact_count": len(artifacts),
        "artifact_bytes": artifact_bytes,
        "workspace_count": len(workspaces),
        "workspace_bytes": workspace_bytes,
        "total_bytes": artifact_bytes + workspace_bytes,
        "artifacts": [
            {
                "id": artifact.id,
                "artifact_type": artifact.artifact_type,
                "uri": artifact.uri,
                "content_hash": artifact.content_hash,
                "size_bytes": artifact.size_bytes or 0,
                "metadata": artifact.metadata_json,
                "exists": Path(artifact.uri).exists() if artifact.uri and "://" not in artifact.uri else None,
            }
            for artifact in artifacts
        ],
        "workspaces": workspaces,
    }
