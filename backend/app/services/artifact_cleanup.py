from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Experiment, ExperimentCleanRun, TestReplay
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
