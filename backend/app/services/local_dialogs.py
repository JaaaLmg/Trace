from __future__ import annotations

from pathlib import Path


def _initial_directory(initial_path: str | None) -> str:
    if not initial_path:
        return str(Path.home())

    try:
        path = Path(initial_path).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return str(Path.home())

    if path.is_dir():
        return str(path)
    if path.parent.is_dir():
        return str(path.parent)
    return str(Path.home())


def pick_directory(*, initial_path: str | None = None, title: str | None = None) -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:  # pragma: no cover - depends on host Python build
        raise RuntimeError("local directory picker is unavailable in this Python environment") from exc

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass

    try:
        selected = filedialog.askdirectory(
            parent=root,
            initialdir=_initial_directory(initial_path),
            title=title or "Select project folder",
            mustexist=True,
        )
    except tk.TclError as exc:
        raise RuntimeError(f"local directory picker failed: {exc}") from exc
    finally:
        root.destroy()

    if not selected:
        return None
    return str(Path(selected).expanduser().resolve())
