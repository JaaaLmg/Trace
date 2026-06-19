from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.final_attempts import final_attempts_from_records
from app.models import (
    BugVariant,
    EvalTask,
    Experiment,
    ExperimentCleanRun,
    ExperimentReplayRun,
    ExperimentStrategyVersion,
    PytestCaseResult,
    RunArtifact,
    RunAttempt,
    RunPlanItem,
    SeededBug,
    Strategy,
    TestReplay,
    TestReport,
    TestRun,
)
from app.repositories.strategies import get_strategy_version
from app.services.evaluation import EvaluationNotFoundError
from app.services.evaluation_events import build_reflection_event_backfeed_audit, project_evaluation_events
from eval.harness import metrics as harness_metrics


@dataclass
class MetricRun:
    strategy_id: str
    strategy_name: str
    repeat: int
    status: str
    clean_passed: set[str]
    clean_failed: bool
    n_cases: int
    tokens: int
    tool_calls: int
    reflection_used: bool
    duration_ms: int = 0
    collection_units: int = 0
    collection_successes: int = 0
    reflection_contract_total: int = 0
    reflection_contract_passed: int = 0
    reflection_acceptance_total: int = 0
    reflection_accepted: int = 0
    invalid_test_set: bool = False
    invalid_reason: str | None = None
    variants: dict = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _experiment_strategy_ids(session: Session, experiment_id: str) -> list[str]:
    stmt = (
        select(ExperimentStrategyVersion)
        .where(ExperimentStrategyVersion.experiment_id == experiment_id)
        .order_by(ExperimentStrategyVersion.index.asc())
    )
    return [row.strategy_version_id for row in session.scalars(stmt)]


def _strategy_key(session: Session, strategy_version_id: str) -> str:
    sv = get_strategy_version(session, strategy_version_id)
    return (sv.strategy_id or sv.id) if sv is not None else strategy_version_id


def _strategy_parent_name(session: Session, strategy_version_id: str) -> str:
    sv = get_strategy_version(session, strategy_version_id)
    if sv is None:
        return strategy_version_id
    parent = session.get(Strategy, sv.strategy_id) if sv.strategy_id else None
    return parent.name if parent is not None else sv.name


def _final_attempt_ids(session: Session, run_id: str) -> set[str]:
    attempts = list(
        session.scalars(
            select(RunAttempt)
            .join_from(RunAttempt, RunPlanItem)
            .where(RunPlanItem.run_id == run_id)
            .order_by(RunAttempt.attempt_no.asc())
        )
    )
    results = list(
        session.scalars(
            select(PytestCaseResult)
            .join_from(PytestCaseResult, RunAttempt)
            .join_from(RunAttempt, RunPlanItem)
            .where(RunPlanItem.run_id == run_id)
        )
    )
    return {attempt.id for attempt in final_attempts_from_records(attempts, results).values()}


def _final_pytest_duration_ms(session: Session, run_id: str) -> int:
    final_ids = _final_attempt_ids(session, run_id)
    if not final_ids:
        return 0
    return sum(
        int(result.duration_ms or 0)
        for result in session.scalars(select(PytestCaseResult).where(PytestCaseResult.attempt_id.in_(final_ids)))
    )


def list_clean_runs(session: Session, experiment_id: str) -> list[ExperimentCleanRun]:
    if session.get(Experiment, experiment_id) is None:
        raise EvaluationNotFoundError("experiment not found")
    stmt = (
        select(ExperimentCleanRun)
        .where(ExperimentCleanRun.experiment_id == experiment_id)
        .order_by(ExperimentCleanRun.created_at.asc(), ExperimentCleanRun.id.asc())
    )
    return list(session.scalars(stmt))


def list_replay_runs(session: Session, experiment_id: str) -> list[TestReplay]:
    if session.get(Experiment, experiment_id) is None:
        raise EvaluationNotFoundError("experiment not found")
    stmt = (
        select(TestReplay)
        .join_from(TestReplay, ExperimentCleanRun)
        .where(ExperimentCleanRun.experiment_id == experiment_id)
        .order_by(TestReplay.created_at.asc(), TestReplay.id.asc())
    )
    return list(session.scalars(stmt))


def _reflection_evidence(metrics: dict) -> dict:
    quality = metrics.get("report_quality") or {}
    evidence = quality.get("reflection_evidence") if isinstance(quality, dict) else {}
    return evidence if isinstance(evidence, dict) else {}


def _metric_detail_for_clean(session: Session, clean: ExperimentCleanRun, run: TestRun | None, metrics: dict) -> dict:
    replay_rows = list(
        session.scalars(
            select(TestReplay)
            .where(TestReplay.experiment_clean_run_id == clean.id)
            .order_by(TestReplay.created_at.asc(), TestReplay.id.asc())
        )
    )
    final_collection_errors = int((clean.clean_metrics or {}).get("collection_errors", 0))
    invalid_test_set = (clean.clean_metrics or {}).get("validity_status") == "invalid_test_set"
    collection_units = 1 + len(replay_rows)
    collection_successes = 1 if final_collection_errors == 0 and not invalid_test_set else 0
    replay_duration = 0
    for replay_row in replay_rows:
        summary = replay_row.pytest_summary or {}
        replay_duration += int(summary.get("duration_ms") or 0)
        if int(summary.get("collection_errors") or 0) == 0 and replay_row.error_code is None:
            collection_successes += 1

    # reflection 的单一真相口径：是否发生、契约是否通过、是否被采纳，全部从 report 写的
    # reflection_evidence 读。别再混用顶层 metrics["reflection_used"]，否则分母/分子两处来源会漂。
    evidence = _reflection_evidence(metrics)
    reflection_used = bool(evidence.get("used"))
    accepted_attempt_id = evidence.get("accepted_attempt_id")
    contract_passed = evidence.get("contract_passed")
    contract_total = 1 if reflection_used else 0
    contract_ok = 1 if reflection_used and contract_passed is True else 0
    acceptance_total = 1 if reflection_used else 0
    accepted = 1 if reflection_used and accepted_attempt_id else 0

    return {
        "duration_ms": _final_pytest_duration_ms(session, clean.clean_run_id) + replay_duration,
        "collection_units": collection_units,
        "collection_successes": collection_successes,
        "reflection_used": reflection_used,
        "reflection_contract_total": contract_total,
        "reflection_contract_passed": contract_ok,
        "reflection_acceptance_total": acceptance_total,
        "reflection_accepted": accepted,
    }


def _metric_runs(session: Session, experiment_id: str) -> dict[str, list[MetricRun]]:
    stmt = (
        select(ExperimentCleanRun)
        .where(ExperimentCleanRun.experiment_id == experiment_id)
        .order_by(ExperimentCleanRun.strategy_version_id.asc(), ExperimentCleanRun.repeat_index.asc())
    )
    grouped: dict[str, dict[int, MetricRun]] = {}
    for clean in session.scalars(stmt):
        run = session.get(TestRun, clean.clean_run_id)
        report = session.scalar(select(TestReport).where(TestReport.run_id == clean.clean_run_id))
        metrics = report.metrics if report is not None else {}
        replay_stmt = (
            select(ExperimentReplayRun)
            .where(ExperimentReplayRun.experiment_clean_run_id == clean.id)
            .order_by(ExperimentReplayRun.bug_variant_id.asc())
        )
        variants = {}
        for replay_result in session.scalars(replay_stmt):
            variants[replay_result.bug_variant_id] = {
                "captured": replay_result.captured_bug,
                "capturing_tests": replay_result.replay_metrics.get("capturing_nodeids", []),
            }
        sid = _strategy_key(session, clean.strategy_version_id)
        detail = _metric_detail_for_clean(session, clean, run, metrics)
        clean_metrics = clean.clean_metrics or {}
        invalid_test_set = clean_metrics.get("validity_status") == "invalid_test_set"
        invalid_reason = clean_metrics.get("invalid_reason")
        repeat_runs = grouped.setdefault(sid, {})
        existing = repeat_runs.get(clean.repeat_index)
        if existing is None:
            repeat_runs[clean.repeat_index] = MetricRun(
                strategy_id=sid,
                strategy_name=_strategy_parent_name(session, clean.strategy_version_id),
                repeat=clean.repeat_index,
                status=run.status if run is not None else "unknown",
                clean_passed=set(),
                clean_failed=clean.false_positive,
                n_cases=int(clean_metrics.get("final_cases_total", 0)),
                tokens=int(clean_metrics.get("total_tokens", 0)),
                tool_calls=int(clean_metrics.get("tool_call_count", 0)),
                reflection_used=detail["reflection_used"],
                duration_ms=detail["duration_ms"],
                collection_units=detail["collection_units"],
                collection_successes=detail["collection_successes"],
                reflection_contract_total=detail["reflection_contract_total"],
                reflection_contract_passed=detail["reflection_contract_passed"],
                reflection_acceptance_total=detail["reflection_acceptance_total"],
                reflection_accepted=detail["reflection_accepted"],
                invalid_test_set=invalid_test_set,
                invalid_reason=str(invalid_reason) if invalid_reason else None,
                variants=variants,
            )
            continue

        existing.clean_failed = existing.clean_failed or clean.false_positive
        existing.n_cases += int(clean_metrics.get("final_cases_total", 0))
        existing.tokens += int(clean_metrics.get("total_tokens", 0))
        existing.tool_calls += int(clean_metrics.get("tool_call_count", 0))
        existing.reflection_used = existing.reflection_used or detail["reflection_used"]
        existing.duration_ms += detail["duration_ms"]
        existing.collection_units += detail["collection_units"]
        existing.collection_successes += detail["collection_successes"]
        existing.reflection_contract_total += detail["reflection_contract_total"]
        existing.reflection_contract_passed += detail["reflection_contract_passed"]
        existing.reflection_acceptance_total += detail["reflection_acceptance_total"]
        existing.reflection_accepted += detail["reflection_accepted"]
        existing.invalid_test_set = existing.invalid_test_set or invalid_test_set
        existing.invalid_reason = existing.invalid_reason or (str(invalid_reason) if invalid_reason else None)
        existing.variants.update(variants)
        run_status = run.status if run is not None else "unknown"
        if existing.status == "completed" and run_status != "completed":
            existing.status = run_status

    return {
        strategy_id: [runs[repeat] for repeat in sorted(runs)]
        for strategy_id, runs in grouped.items()
    }


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _add_v2_metric_fields(rows: list[dict], runs_by_strategy: dict[str, list[MetricRun]]) -> None:
    for row in rows:
        runs = runs_by_strategy.get(row["strategy_id"], [])
        row["avg_duration_ms"] = (sum(run.duration_ms for run in runs) / len(runs)) if runs else 0.0
        collection_units = sum(run.collection_units for run in runs)
        collection_successes = sum(run.collection_successes for run in runs)
        row["pytest_collection_success_rate"] = _rate(collection_successes, collection_units) or 0.0
        contract_total = sum(run.reflection_contract_total for run in runs)
        contract_passed = sum(run.reflection_contract_passed for run in runs)
        row["reflection_contract_pass_rate"] = _rate(contract_passed, contract_total)
        acceptance_total = sum(run.reflection_acceptance_total for run in runs)
        accepted = sum(run.reflection_accepted for run in runs)
        row["reflection_acceptance_rate"] = _rate(accepted, acceptance_total)


def _capture_matrix_variant_ids(session: Session, experiment: Experiment) -> list[str]:
    stmt = (
        select(BugVariant.id)
        .join_from(BugVariant, SeededBug)
        .join_from(SeededBug, EvalTask)
        .where(EvalTask.dataset_id == experiment.dataset_id)
        .order_by(SeededBug.created_at.asc(), SeededBug.id.asc(), BugVariant.created_at.asc(), BugVariant.id.asc())
    )
    return [row for row in session.scalars(stmt)]


def _capture_scope(session: Session, experiment: Experiment) -> dict:
    stmt = (
        select(SeededBug.id, BugVariant.id)
        .join_from(SeededBug, EvalTask)
        .join(BugVariant, BugVariant.seeded_bug_id == SeededBug.id)
        .where(EvalTask.dataset_id == experiment.dataset_id)
        .order_by(SeededBug.created_at.asc(), SeededBug.id.asc(), BugVariant.created_at.asc(), BugVariant.id.asc())
    )
    variants_by_bug: dict[str, list[str]] = {}
    for bug_id, variant_id in session.execute(stmt):
        variants_by_bug.setdefault(bug_id, []).append(variant_id)
    return {
        "unit": "bug_variant",
        "total_seeded_bugs": len(variants_by_bug),
        "total_bug_variants": sum(len(variants) for variants in variants_by_bug.values()),
        "single_variant_per_seeded_bug": all(len(variants) == 1 for variants in variants_by_bug.values()),
        "variants_per_seeded_bug": {bug_id: len(variants) for bug_id, variants in variants_by_bug.items()},
    }


def _capture_matrix_counts(variant_ids: list[str], runs_by_strategy: dict[str, list[MetricRun]]) -> dict:
    matrix: dict[str, dict[str, dict[str, int | float | bool]]] = {}
    for variant_id in variant_ids:
        matrix[variant_id] = {}
        for strategy_id, runs in runs_by_strategy.items():
            evaluable_runs = [run for run in runs if not run.invalid_test_set]
            captured_count = sum(
                1 for run in evaluable_runs if run.variants.get(variant_id, {}).get("captured")
            )
            repeat_count = len(evaluable_runs)
            matrix[variant_id][strategy_id] = {
                "captured": captured_count > 0,
                "captured_count": captured_count,
                "repeat_count": repeat_count,
                "capture_rate": (captured_count / repeat_count) if repeat_count else 0.0,
            }
    return matrix


def _auto_mutation_variant_scope(session: Session, experiment: Experiment) -> tuple[list[str], dict[str, int]]:
    stmt = (
        select(BugVariant)
        .join_from(BugVariant, SeededBug)
        .join_from(SeededBug, EvalTask)
        .where(EvalTask.dataset_id == experiment.dataset_id)
        .order_by(SeededBug.created_at.asc(), SeededBug.id.asc(), BugVariant.created_at.asc(), BugVariant.id.asc())
    )
    variant_ids: list[str] = []
    excluded_counts: dict[str, int] = {}
    for variant in session.scalars(stmt):
        ground_truth = variant.ground_truth or {}
        if ground_truth.get("source") != "auto_mutation":
            excluded_counts["non_auto_mutation"] = excluded_counts.get("non_auto_mutation", 0) + 1
            continue
        probe = ground_truth.get("probe") if isinstance(ground_truth.get("probe"), dict) else {}
        probe_check = probe.get("probe_check") if isinstance(probe.get("probe_check"), dict) else {}
        if probe_check.get("status") != "passed":
            excluded_counts["probe_check_not_passed"] = excluded_counts.get("probe_check_not_passed", 0) + 1
            continue
        variant_ids.append(variant.id)
    return variant_ids, excluded_counts


def _sampled_mutation_matrix_counts(variant_ids: list[str], runs_by_strategy: dict[str, list[MetricRun]]) -> dict:
    matrix: dict[str, dict[str, dict[str, int | float | bool]]] = {}
    for variant_id in variant_ids:
        matrix[variant_id] = {}
        for strategy_id, runs in runs_by_strategy.items():
            evaluable_runs = [run for run in runs if not run.invalid_test_set]
            replayed_count = sum(1 for run in evaluable_runs if variant_id in run.variants)
            captured_count = sum(
                1
                for run in evaluable_runs
                if run.variants.get(variant_id, {}).get("captured")
            )
            repeat_count = len(evaluable_runs)
            matrix[variant_id][strategy_id] = {
                "captured": captured_count > 0,
                "captured_count": captured_count,
                "replayed_count": replayed_count,
                "repeat_count": repeat_count,
                "capture_rate": (captured_count / replayed_count) if replayed_count else 0.0,
            }
    return matrix


def _sampled_mutation_score(
    session: Session,
    experiment: Experiment,
    rows: list[dict],
    runs_by_strategy: dict[str, list[MetricRun]],
) -> dict:
    variant_ids, excluded_counts = _auto_mutation_variant_scope(session, experiment)
    matrix_counts = _sampled_mutation_matrix_counts(variant_ids, runs_by_strategy)
    score_rows = []
    for row in rows:
        strategy_id = row["strategy_id"]
        runs = [run for run in runs_by_strategy.get(strategy_id, []) if not run.invalid_test_set]
        repeat_count = len(runs)
        expected_replay_count = len(variant_ids) * repeat_count
        observed_replay_count = sum(
            stats[strategy_id]["replayed_count"]
            for stats in matrix_counts.values()
            if strategy_id in stats
        )
        captured_mutant_count = sum(
            1
            for stats in matrix_counts.values()
            if strategy_id in stats and stats[strategy_id]["captured"]
        )
        if not variant_ids:
            status = "not_applicable"
            score = None
        elif expected_replay_count == 0 or observed_replay_count != expected_replay_count:
            status = "incomplete_replay"
            score = None
        else:
            status = "ok"
            score = captured_mutant_count / len(variant_ids)
        score_rows.append(
            {
                "strategy_id": strategy_id,
                "strategy_name": row["strategy_name"],
                "mutant_count": len(variant_ids),
                "repeat_count": repeat_count,
                "expected_replay_count": expected_replay_count,
                "observed_replay_count": observed_replay_count,
                "captured_mutant_count": captured_mutant_count,
                "score": score,
                "status": status,
            }
        )

    if not variant_ids:
        status = "not_applicable"
    elif not score_rows or any(row["status"] == "incomplete_replay" for row in score_rows):
        status = "incomplete_replay"
    else:
        status = "ok"
    return {
        "status": status,
        "unit": "auto_mutation_bug_variant",
        "denominator_source": (
            "bug_variants.ground_truth.source=auto_mutation + "
            "ground_truth.probe.probe_check.status=passed"
        ),
        "mutant_count": len(variant_ids),
        "included_variant_ids": variant_ids,
        "excluded_variant_counts": excluded_counts,
        "rows": score_rows,
        "matrix_counts": matrix_counts,
    }


def _data_source(experiment: Experiment, rows: list[dict]) -> dict:
    providers = []
    models = []
    for row in rows:
        display = row.get("llm_display") or {}
        providers.append(display.get("provider"))
        models.append(display.get("model"))
    provider = next((p for p in providers if p), None)
    model = next((m for m in models if m), None)
    kind = "mock" if provider == "mock" else "real_llm"
    return {
        "kind": kind,
        "label": "Database experiment metrics",
        "provider_label": provider,
        "model_label": model,
        "generated_by": "experiment_service",
    }


def _fallback_report_quality(clean: ExperimentCleanRun) -> dict:
    clean_metrics = clean.clean_metrics or {}
    context = clean_metrics.get("context_completeness")
    if not isinstance(context, dict):
        context = {
            "status": "incomplete",
            "context_incomplete": True,
            "snippets": [],
            "missing_targets": [],
            "risk_notes": ["source context was not collected"],
        }
    return {
        "test_inventory": [],
        "target_mappings": [],
        "assertion_summaries": [],
        "failure_classifications": [],
        "reflection_evidence": {
            "used": False,
            "contract_checked": False,
            "contract_passed": None,
            "violation_reasons": [],
            "accepted_attempt_id": None,
            "rejected_attempt_ids": [],
        },
        "context_completeness": context,
    }


def _clean_run_payload(session: Session, clean: ExperimentCleanRun) -> dict:
    run = session.get(TestRun, clean.clean_run_id)
    report = session.scalar(select(TestReport).where(TestReport.run_id == clean.clean_run_id))
    report_quality = ((report.metrics or {}).get("report_quality", {}) if report is not None else {})
    if not report_quality:
        report_quality = _fallback_report_quality(clean)
    return {
        "id": clean.id,
        "experiment_id": clean.experiment_id,
        "eval_task_id": clean.eval_task_id,
        "strategy_version_id": clean.strategy_version_id,
        "repeat_index": clean.repeat_index,
        "clean_run_id": clean.clean_run_id,
        "status": run.status if run is not None else "unknown",
        "generated_test_set_artifact_id": clean.generated_test_set_artifact_id,
        "false_positive": clean.false_positive,
        "clean_metrics": clean.clean_metrics,
        "runtime_snapshot": (run.runtime_snapshot or {}) if run is not None else {},
        "strategy_snapshot": (run.strategy_snapshot or {}) if run is not None else {},
        "report_quality": report_quality,
    }


def get_experiment_metrics(session: Session, experiment_id: str) -> dict:
    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        raise EvaluationNotFoundError("experiment not found")
    runs_by_strategy = _metric_runs(session, experiment_id)
    total_in_scope = len(_capture_matrix_variant_ids(session, experiment))
    rows = harness_metrics.aggregate(runs_by_strategy, total_in_scope=total_in_scope)
    _add_v2_metric_fields(rows, runs_by_strategy)

    for row in rows:
        clean_run_ids = [
            clean.clean_run_id
            for clean in session.scalars(
                select(ExperimentCleanRun)
                .where(ExperimentCleanRun.experiment_id == experiment_id)
                .order_by(ExperimentCleanRun.repeat_index.asc())
            )
            if _strategy_key(session, clean.strategy_version_id) == row["strategy_id"]
        ]
        first_run = session.get(TestRun, clean_run_ids[0]) if clean_run_ids else None
        resolved = ((first_run.strategy_snapshot or {}).get("resolved_llm") or {}) if first_run is not None else {}
        row["cost_per_captured_bug_status"] = "ok" if row["cost_per_captured_bug"] is not None else "no_bug_captured"
        row["data_source"] = "mock" if resolved.get("provider") == "mock" else "real_llm"
        row["llm_display"] = {
            "provider": resolved.get("provider", "unknown"),
            "model": resolved.get("model", "unknown"),
            "derived_from_clean_run_ids": clean_run_ids,
            "source": "derived_from_clean_run_strategy_snapshots",
        }

    variant_ids = _capture_matrix_variant_ids(session, experiment)
    matrix_counts = _capture_matrix_counts(variant_ids, runs_by_strategy)
    matrix = {
        variant_id: {
            strategy_id: bool(stats.get("captured"))
            for strategy_id, stats in by_strategy.items()
        }
        for variant_id, by_strategy in matrix_counts.items()
    }
    # Keep the harness function in the call path for synthetic parity while using DB variant ids.
    if not variant_ids:
        matrix = {}

    clean_runs = list_clean_runs(session, experiment_id)
    replays = list_replay_runs(session, experiment_id)
    replay_results = list(
        session.scalars(
            select(ExperimentReplayRun)
            .join_from(ExperimentReplayRun, ExperimentCleanRun)
            .where(ExperimentCleanRun.experiment_id == experiment_id)
            .order_by(ExperimentReplayRun.created_at.asc(), ExperimentReplayRun.id.asc())
        )
    )
    artifact_ids = {
        clean.generated_test_set_artifact_id
        for clean in clean_runs
        if clean.generated_test_set_artifact_id
    }
    artifact_ids.update(
        replay.generated_test_set_artifact_id
        for replay in replays
        if replay.generated_test_set_artifact_id
    )
    artifacts = []
    if artifact_ids:
        artifacts = list(
            session.scalars(
                select(RunArtifact)
                .where(RunArtifact.artifact_type == "generated_test_set")
                .where(RunArtifact.id.in_(artifact_ids))
                .order_by(RunArtifact.created_at.asc(), RunArtifact.id.asc())
            )
        )
    evaluation_events = project_evaluation_events(experiment, clean_runs, replays, replay_results)

    return {
        "schema_version": "v2.phase0",
        "generated_at": _now().isoformat(),
        "data_source": _data_source(experiment, rows),
        "experiment": {
            "id": experiment.id,
            "name": experiment.name,
            "dataset_id": experiment.dataset_id,
            "strategy_version_ids": _experiment_strategy_ids(session, experiment.id),
            "repeat_count": experiment.repeat_count,
            "llm_override": experiment.llm_override,
            "status": experiment.status,
            "created_at": experiment.created_at.isoformat(),
            "started_at": _iso(experiment.started_at),
            "finished_at": _iso(experiment.finished_at),
            "error_code": experiment.error_code,
            "error_message": experiment.error_message,
        },
        "source_context_policy": {
            "project_root_boundary": "project_snapshot_root",
            "read_allowlist_globs": ["**/*.py"],
            "deny_globs": ["../**", "tests/generated/**"],
            "generated_tests_dir": "tests/generated",
            "max_file_bytes": 64000,
            "max_total_bytes": 128000,
            "max_snippets": 12,
            "trace_payload_required": True,
            "missing_context_marker": "context_incomplete",
            "agent_source_write_permission": "generated_tests_only",
        },
        "capture_scope": _capture_scope(session, experiment),
        "rows": rows,
        "capture_matrix": matrix,
        "capture_matrix_counts": matrix_counts,
        "sampled_mutation_score": _sampled_mutation_score(session, experiment, rows, runs_by_strategy),
        "clean_runs": [_clean_run_payload(session, clean) for clean in clean_runs],
        "replay_runs": [
            {
                "id": replay_row.id,
                "experiment_clean_run_id": replay_row.experiment_clean_run_id,
                "generated_test_set_artifact_id": replay_row.generated_test_set_artifact_id,
                "target_snapshot_id": replay_row.target_snapshot_id,
                "bug_variant_id": replay_row.bug_variant_id,
                "status": replay_row.status,
                "pytest_summary": {
                    "collected": int((replay_row.pytest_summary or {}).get("collected", 0)),
                    "passed": int((replay_row.pytest_summary or {}).get("passed", 0)),
                    "failed": int((replay_row.pytest_summary or {}).get("failed", 0)),
                    "skipped": int((replay_row.pytest_summary or {}).get("skipped", 0)),
                    "collection_errors": int((replay_row.pytest_summary or {}).get("collection_errors", 0)),
                    "duration_ms": (replay_row.pytest_summary or {}).get("duration_ms"),
                },
                "replay_mode": replay_row.replay_mode,
                "llm_calls": replay_row.llm_calls,
                "started_at": _iso(replay_row.started_at),
                "finished_at": _iso(replay_row.finished_at),
                "error_code": replay_row.error_code,
                "error_message": replay_row.error_message,
            }
            for replay_row in replays
        ],
        "experiment_replay_runs": [
            {
                "id": replay_result.id,
                "experiment_clean_run_id": replay_result.experiment_clean_run_id,
                "bug_variant_id": replay_result.bug_variant_id,
                "replay_id": replay_result.replay_id,
                "captured_bug": replay_result.captured_bug,
                "replay_metrics": replay_result.replay_metrics,
            }
            for replay_result in replay_results
        ],
        "evaluation_events": evaluation_events,
        "reflection_event_backfeed": build_reflection_event_backfeed_audit(clean_runs, evaluation_events),
        "artifacts": [
            {
                "id": artifact.id,
                "artifact_type": artifact.artifact_type,
                "uri": artifact.uri,
                "content_hash": artifact.content_hash,
                "size_bytes": artifact.size_bytes or 0,
                "metadata": artifact.metadata_json,
            }
            for artifact in artifacts
        ],
    }
