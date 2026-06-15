from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.schemas.evaluation import ContextCompletenessEvidence, SourceContextSnippet
from app.tools.base import ToolContext
from app.tools.fs_tools import read_file
from app.schemas.tools import ReadFileInput


@dataclass(frozen=True)
class SourceContextBundle:
    snippets: list[SourceContextSnippet]
    context_completeness: ContextCompletenessEvidence
    source_context_text: str


def build_source_context_bundle(ctx: ToolContext, target_scope: list[str], *, max_file_bytes: int = 24000, max_total_bytes: int = 48000, max_snippets: int = 12) -> SourceContextBundle:
    snippets: list[SourceContextSnippet] = []
    pieces: list[str] = []
    total_bytes = 0
    missing_targets: list[str] = []
    risk_notes: list[str] = []

    candidates = _candidate_paths(ctx, target_scope)
    for rel_path in candidates[:max_snippets]:
        try:
            out = read_file(ctx, ReadFileInput(path=rel_path, max_bytes=max_file_bytes))
        except Exception:
            missing_targets.append(rel_path)
            continue
        if total_bytes + out.bytes > max_total_bytes:
            risk_notes.append("source context truncated by max_total_bytes")
            break
        total_bytes += out.bytes
        content_hash = hashlib.sha256(out.content.encode("utf-8")).hexdigest()
        snippets.append(
            SourceContextSnippet(
                path=out.path,
                target_ref=Path(rel_path).stem,
                start_line=1,
                end_line=max(1, out.content.count("\n") + 1),
                content_hash=content_hash,
                bytes=out.bytes,
            )
        )
        pieces.append(f"## {out.path}\n```python\n{out.content}\n```")

    if not snippets:
        status = "incomplete"
        risk_notes.append("no source snippet could be read")
    elif missing_targets:
        status = "partial"
        risk_notes.append("some source targets were unavailable")
    else:
        status = "complete"

    context = ContextCompletenessEvidence(
        status=status,
        context_incomplete=status != "complete",
        snippets=snippets,
        missing_targets=missing_targets,
        risk_notes=risk_notes,
    )
    return SourceContextBundle(
        snippets=snippets,
        context_completeness=context,
        source_context_text="\n\n".join(pieces),
    )


def _candidate_paths(ctx: ToolContext, target_scope: list[str]) -> list[str]:
    if target_scope:
        return [str(p).replace("\\", "/") for p in target_scope]
    defaults = ["calc.py", "app.py", "main.py"]
    return [path for path in defaults if (ctx.root / path).exists()]
