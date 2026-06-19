from __future__ import annotations

import hashlib

from app.schemas.evaluation import SourceContextRetrievalTrace


def source_context_trace_id(*parts: object) -> str:
    raw = "\0".join("" if part is None else str(part) for part in parts)
    return "ctx-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def make_source_context_trace(
    *,
    target: str,
    source_kind: str,
    retrieval_source: str,
    status: str,
    confidence: float,
    trace_id: str | None = None,
    source_path: str | None = None,
    symbol: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    content_hash: str | None = None,
    risk_notes: list[str] | None = None,
) -> SourceContextRetrievalTrace:
    line_range = {"start": start_line, "end": end_line} if start_line is not None and end_line is not None else None
    return SourceContextRetrievalTrace(
        trace_id=trace_id
        or source_context_trace_id(
            target,
            source_kind,
            retrieval_source,
            source_path or "",
            symbol or "",
            status,
            content_hash or "",
        ),
        source_kind=source_kind,  # type: ignore[arg-type]
        retrieval_source=retrieval_source,  # type: ignore[arg-type]
        target=target,
        source_path=safe_source_path(source_path),
        symbol=symbol,
        line_range=line_range,
        confidence=confidence,
        content_hash=content_hash,
        status=status,  # type: ignore[arg-type]
        risk_notes=risk_notes or [],
    )


def safe_source_path(path: str | None) -> str | None:
    if not path:
        return None
    norm = path.replace("\\", "/").strip()
    if not norm or norm.startswith("/") or norm.startswith("//") or (len(norm) >= 2 and norm[1] == ":"):
        return None
    if any(part == ".." for part in norm.split("/")):
        return None
    return norm