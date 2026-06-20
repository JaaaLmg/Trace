from __future__ import annotations

from dataclasses import dataclass

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


def support_targets(ctx: ToolContext, analysis: AnalyzeProjectOutput) -> list[SupportTarget]:
    generated_tests_dir = ctx.relpath(ctx.test_write_dir)
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
        for test in test_file.test_functions:
            targets.append(
                SupportTarget(
                    raw=f"existing_test:{test.estimated_nodeid}",
                    rel_path=test_file.path,
                    symbol=test.name,
                    source_kind="existing_test",
                    retrieval_source="pytest_scanner",
                    confidence=0.9,
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