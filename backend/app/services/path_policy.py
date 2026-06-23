from __future__ import annotations

from pathlib import Path

TRACE_ROOT = Path(__file__).resolve().parents[3]


def _resolve_path(path: str | Path) -> Path:
    try:
        return Path(path).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(f"path cannot be resolved: {exc}") from exc


def _relative_to_trace_root(path: Path) -> Path | None:
    try:
        return path.relative_to(TRACE_ROOT)
    except ValueError:
        return None


def is_trace_internal_tmp_path(path: str | Path) -> bool:
    path = _resolve_path(path)
    relative = _relative_to_trace_root(path)
    if relative is None or not relative.parts:
        return False
    return relative.parts[0].lower().startswith(".pytest_tmp")


def is_trace_experiment_workspace_path(path: str | Path) -> bool:
    path = _resolve_path(path)
    relative = _relative_to_trace_root(path)
    if relative is None or not relative.parts:
        return False
    return relative.parts[0].lower() == ".pytest_tmp_experiments"


def validate_project_root(path: str | Path) -> Path:
    root = _resolve_path(path)
    try:
        if not root.exists():
            raise ValueError("project path does not exist")
        if not root.is_dir():
            raise ValueError("project path is not a directory")
        # Touch the iterator so unreadable directories fail at validation time.
        next(root.iterdir(), None)
    except ValueError:
        raise
    except OSError as exc:
        raise ValueError(f"project path is not accessible: {exc}") from exc
    return root


def is_valid_project_root(path: str | Path) -> bool:
    try:
        validate_project_root(path)
    except ValueError:
        return False
    return True


def validate_snapshot_root(path: str | Path, *, project_root: str | Path) -> Path:
    root = validate_project_root(path)
    project = validate_project_root(project_root)
    if is_trace_experiment_workspace_path(root):
        return root
    try:
        root.relative_to(project)
    except ValueError as exc:
        raise ValueError("snapshot root must be inside project path") from exc
    return root


def ensure_generated_tests_dir(snapshot_root: str | Path) -> Path:
    root = validate_project_root(snapshot_root)
    test_write_dir = root / "tests" / "generated"
    try:
        test_write_dir.mkdir(parents=True, exist_ok=True)
        if not test_write_dir.is_dir():
            raise ValueError("generated tests path is not a directory")
    except ValueError:
        raise
    except OSError as exc:
        raise ValueError(f"generated tests directory is not writable: {exc}") from exc
    return test_write_dir
