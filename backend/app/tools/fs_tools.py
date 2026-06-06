from __future__ import annotations

import fnmatch
from pathlib import Path

from app.core.errors import ErrorCode, TraceError
from app.schemas.tools import (
    FileEntry,
    ListFilesInput,
    ListFilesOutput,
    ReadFileInput,
    ReadFileOutput,
)
from app.tools.base import ToolContext

_IGNORE = {".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache"}


def list_files(ctx: ToolContext, inp: ListFilesInput) -> ListFilesOutput:
    base = ctx.resolve_read(inp.path)
    if base.is_file():
        return ListFilesOutput(
            entries=[FileEntry(path=ctx.relpath(base), is_dir=False, size=base.stat().st_size)]
        )

    entries: list[FileEntry] = []
    truncated = False
    for p in sorted(base.rglob("*")):
        if any(part in _IGNORE for part in p.relative_to(base).parts):
            continue
        if inp.glob and not p.is_dir() and not fnmatch.fnmatch(p.name, inp.glob):
            continue
        entries.append(
            FileEntry(
                path=ctx.relpath(p),
                is_dir=p.is_dir(),
                size=(p.stat().st_size if p.is_file() else 0),
            )
        )
        if len(entries) >= inp.max_entries:
            truncated = True
            break
    return ListFilesOutput(entries=entries, truncated=truncated)


def read_file(ctx: ToolContext, inp: ReadFileInput) -> ReadFileOutput:
    p = ctx.resolve_read(inp.path)
    if not p.is_file():
        raise TraceError(ErrorCode.TOOL_ARGUMENT_ERROR, f"不是文件或不存在：{inp.path}")
    data = p.read_bytes()
    truncated = len(data) > inp.max_bytes
    content = data[: inp.max_bytes].decode("utf-8", errors="replace")
    return ReadFileOutput(path=ctx.relpath(p), content=content, truncated=truncated, bytes=len(data))
