from __future__ import annotations

from pathlib import Path

import pytest

from app.services.artifact_cleanup import CleanupError, _safe_cleanup_path
from app.services.experiments import EXPERIMENT_WORK_ROOT


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
