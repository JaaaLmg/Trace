from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.schemas.evaluation import SourceContextRetrievalTrace
from app.schemas.tools import AnalyzeProjectOutput
from app.tools.base import ToolContext

_SUPPORT_CONTEXT_KINDS = {"dependency", "reference", "model_schema", "fixture", "existing_test", "failure_context"}


@dataclass(frozen=True)
class SupportTarget:
    raw: str
    rel_path: str
    symbol: str | None
    source_kind: str
    retrieval_source: str
    confidence: float


def support_targets(
    ctx: ToolContext,
    analysis: AnalyzeProjectOutput,
    *,
    target_source_paths: set[str] | None = None,
    target_symbols: set[str] | None = None,
) -> list[SupportTarget]:
    generated_tests_dir = ctx.relpath(ctx.test_write_dir)
    target_source_paths = {path.replace("\\", "/") for path in (target_source_paths or set())}
    target_symbols = {symbol for symbol in (target_symbols or set()) if symbol}
    targets: list[SupportTarget] = []
    for model in analysis.models:
        targets.append(
            SupportTarget(
                raw=f"model:{model.name}",
                rel_path=model.file,
                symbol=model.name,
                source_kind="model_schema",
                retrieval_source="analysis_ast",
                confidence=0.95,
            )
        )
    for fixture in analysis.fixtures:
        if is_generated_test_path(fixture.file, generated_tests_dir):
            continue
        targets.append(
            SupportTarget(
                raw=f"fixture:{fixture.name}",
                rel_path=fixture.file,
                symbol=fixture.name,
                source_kind="fixture",
                retrieval_source="pytest_scanner",
                confidence=0.95,
            )
        )
    for test_file in analysis.existing_tests:
        if is_generated_test_path(test_file.path, generated_tests_dir):
            continue
        test_source = _read_support_text(ctx, test_file.path)
        for test in test_file.test_functions:
            confidence = _existing_test_confidence(
                test_file.path,
                test.name,
                test_source,
                target_source_paths=target_source_paths,
                target_symbols=target_symbols,
            )
            targets.append(
                SupportTarget(
                    raw=f"existing_test:{test.estimated_nodeid}",
                    rel_path=test_file.path,
                    symbol=test.name,
                    source_kind="existing_test",
                    retrieval_source="pytest_scanner",
                    confidence=confidence,
                )
            )
    return targets


def dedupe_support_targets(
    targets: list[SupportTarget],
    seen: set[tuple[str, str | None]],
) -> tuple[list[SupportTarget], list[tuple[SupportTarget, SupportTarget | None]]]:
    unique: list[SupportTarget] = []
    duplicates: list[tuple[SupportTarget, SupportTarget | None]] = []
    occupied = set(seen)
    kept_by_key: dict[tuple[str, str | None], SupportTarget] = {}
    for target in targets:
        key = (target.rel_path, target.symbol)
        if key in occupied:
            duplicates.append((target, kept_by_key.get(key)))
            continue
        occupied.add(key)
        kept_by_key[key] = target
        unique.append(target)
    return unique, duplicates


def support_dedup_note(kept: SupportTarget | None) -> str:
    if kept is None:
        return "support context deduplicated by evidence key; existing snippet already covers this path/symbol"
    return f"support context deduplicated by evidence key; kept {kept.raw}"


def support_context_incomplete(retrieval_trace: list[SourceContextRetrievalTrace]) -> bool:
    return any(trace.source_kind in _SUPPORT_CONTEXT_KINDS and trace.status != "resolved" for trace in retrieval_trace)


def is_generated_test_path(path: str, generated_tests_dir: str) -> bool:
    norm = path.replace("\\", "/").strip("/")
    generated = generated_tests_dir.replace("\\", "/").strip("/")
    return bool(generated) and (norm == generated or norm.startswith(generated + "/"))


def _read_support_text(ctx: ToolContext, rel_path: str, max_chars: int = 64_000) -> str:
    try:
        path = ctx.resolve_read(rel_path)
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except Exception:
        return ""


def _existing_test_confidence(
    path: str,
    test_name: str,
    source: str,
    *,
    target_source_paths: set[str],
    target_symbols: set[str],
) -> float:
    segment = _test_segment(source, test_name) or source
    label = f"{path}::{test_name}".lower()
    confidence = 0.62

    if target_symbols:
        if any(_contains_identifier(segment, symbol) for symbol in target_symbols):
            confidence += 0.12
        elif any(_contains_identifier(source, symbol) for symbol in target_symbols):
            confidence += 0.04

    module_tokens = _module_tokens(target_source_paths)
    if module_tokens and any(_contains_identifier(source, token) or token in source for token in module_tokens):
        confidence += 0.03

    if "pytest.raises" in segment or " raises(" in segment:
        confidence += 0.08
    if "strict" in label or "strict" in segment.lower():
        confidence += 0.06
    confidence += min(0.06, 0.02 * _target_keyword_overlap(label, segment, target_symbols, target_source_paths))
    if any(token in path.lower() for token in module_tokens):
        confidence += 0.02

    return min(confidence, 1.0)


def _module_tokens(paths: set[str]) -> set[str]:
    tokens: set[str] = set()
    for raw in paths:
        path = PurePosixPath(raw.replace("\\", "/"))
        stem = path.stem
        if stem and stem != "__init__":
            tokens.add(stem)
        elif path.parent.name:
            tokens.add(path.parent.name)
    return {token for token in tokens if token and token.isidentifier()}


def _target_keyword_overlap(
    label: str,
    segment: str,
    target_symbols: set[str],
    target_source_paths: set[str],
) -> int:
    haystack_tokens = _identifier_tokens(f"{label}\n{segment.lower()}")
    target_tokens = _target_keyword_tokens(target_symbols, target_source_paths)
    return sum(1 for token in target_tokens if token in haystack_tokens)


def _target_keyword_tokens(target_symbols: set[str], target_source_paths: set[str]) -> set[str]:
    tokens: set[str] = set()
    for symbol in target_symbols:
        tokens.update(_identifier_tokens(symbol))
    for path in target_source_paths:
        tokens.update(_identifier_tokens(PurePosixPath(path.replace("\\", "/")).stem))
    stop = {
        "array",
        "char",
        "delimiter",
        "item",
        "json",
        "object",
        "parse",
        "quote",
        "quoted",
        "repair",
        "schema",
        "string",
        "test",
        "value",
    }
    return {token for token in tokens if len(token) >= 3 and token not in stop}


def _identifier_tokens(value: str) -> set[str]:
    return {token.rstrip("s") for token in re.split(r"[^A-Za-z0-9]+|_", value.lower()) if token}


def _contains_identifier(source: str, name: str) -> bool:
    if not name.isidentifier():
        return name in source
    return re.search(rf"(?<!\w){re.escape(name)}(?!\w)", source) is not None


def _test_segment(source: str, test_name: str) -> str:
    if not source:
        return ""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""
    lines = source.splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != test_name:
            continue
        start = getattr(node, "lineno", None)
        end = getattr(node, "end_lineno", None)
        if not start or not end:
            return ""
        return "\n".join(lines[start - 1 : end])
    return ""
