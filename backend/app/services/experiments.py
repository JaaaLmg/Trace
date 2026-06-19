from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.final_attempts import final_attempts_from_records
from app.agents.llm import MockLLM
from app.core.ids import new_id
from app.models import (
    BugVariant,
    EvalDataset,
    EvalTask,
    Experiment,
    ExperimentCleanRun,
    ExperimentReplayRun,
    ExperimentStrategyVersion,
    GeneratedTestFile,
    ProjectSnapshot,
    PytestCaseResult,
    RunArtifact,
    RunAttempt,
    RunPlanItem,
    SeededBug,
    TestReplay,
    TestRun,
)
from app.repositories.strategies import get_strategy_version
from app.schemas.evaluation import EvaluationEventContract, LlmOverride
from app.schemas.tools import AnalyzeProjectInput
from app.services.evaluation import EvaluationConflictError, EvaluationError, EvaluationNotFoundError
from app.services.evaluation_events import (
    build_reflection_event_backfeed,
    project_evaluation_events,
)
from app.services.source_context import build_source_context_bundle
from app.services.test_plans import create_test_plan
from app.services.test_runs import create_run, execute_run_sync
from app.tools.analyze import analyze_project
from app.tools.base import ToolContext
from eval.harness.authors import demo_author
from eval.harness.probes import ProbeCheckError, check_variant_probe
from eval.harness.replay import replay as replay_frozen_tests

TRACE_ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_WORK_ROOT = TRACE_ROOT / ".pytest_tmp_experiments"
FLAKY_CLEAN_REPLAY_RUNS = 3
DEFAULT_REPLAY_TIMEOUT_SECONDS = 60


@dataclass
class FinalTestSet:
    files: dict[str, str]
    clean_passed: set[str]
    clean_failed: bool
    n_cases: int
    collection_errors: int
    final_passed: int
    final_failed: int
    final_skipped: int


class ExperimentError(EvaluationError):
    pass


class ExperimentNotFoundError(ExperimentError, EvaluationNotFoundError):
    pass


class ExperimentConflictError(ExperimentError, EvaluationConflictError):
    pass


class ExperimentCancelledError(ExperimentError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _safe_path_segment(value: str, *, label: str) -> str:
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-")
    if not value or any(char not in allowed for char in value) or ".." in value:
        raise ExperimentError(f"{label} is not a safe path segment")
    return value


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _ensure_experiment_work_path(path: Path) -> Path:
    root = EXPERIMENT_WORK_ROOT.resolve()
    resolved = path.resolve()
    if not _is_relative_to(resolved, root):
        raise ExperimentError(f"experiment work path escapes workspace: {resolved}")
    if resolved == root:
        raise ExperimentError("refusing to operate on experiment work root")
    return resolved


def _experiment_strategy_ids(session: Session, experiment_id: str) -> list[str]:
    stmt = (
        select(ExperimentStrategyVersion)
        .where(ExperimentStrategyVersion.experiment_id == experiment_id)
        .order_by(ExperimentStrategyVersion.index.asc())
    )
    return [row.strategy_version_id for row in session.scalars(stmt)]



def _serialize_experiment(session: Session, experiment: Experiment) -> dict:
    return {
        "id": experiment.id,
        "name": experiment.name,
        "dataset_id": experiment.dataset_id,
        "repeat_count": experiment.repeat_count,
        "llm_override": experiment.llm_override,
        "status": experiment.status,
        "created_at": experiment.created_at,
        "started_at": experiment.started_at,
        "finished_at": experiment.finished_at,
        "error_code": experiment.error_code,
        "error_message": experiment.error_message,
        "strategy_version_ids": _experiment_strategy_ids(session, experiment.id),
    }


def _task_targets(task: EvalTask) -> list[str]:
    scope = task.target_scope or {}
    if isinstance(scope, dict):
        targets = scope.get("targets")
        if isinstance(targets, list):
            return [str(target) for target in targets]
    if isinstance(scope, list):
        return [str(target) for target in scope]
    return []


def _context_gate(snapshot: ProjectSnapshot, targets: list[str]) -> dict:
    root = Path(snapshot.root_path).resolve()
    ctx = ToolContext(root=root, test_write_dir=root / "tests" / "generated")
    analysis = analyze_project(ctx, AnalyzeProjectInput(target_scope=targets))
    bundle = build_source_context_bundle(ctx, targets, analysis)
    blocking = bool(targets) and bundle.context_completeness.context_incomplete
    return {
        "blocking": blocking,
        "reason": "context_incomplete_blocking" if blocking else None,
        "context_completeness": bundle.context_completeness.model_dump(),
        "analysis_warnings": analysis.warnings,
    }


def _empty_final_test_set() -> FinalTestSet:
    return FinalTestSet(
        files={},
        clean_passed=set(),
        clean_failed=False,
        n_cases=0,
        collection_errors=0,
        final_passed=0,
        final_failed=0,
        final_skipped=0,
    )


def _invalid_clean_metrics(run: TestRun, gate: dict) -> dict:
    return {
        "final_cases_total": 0,
        "final_passed": 0,
        "final_failed": 0,
        "final_skipped": 0,
        "collection_errors": 0,
        "tool_call_count": run.tool_call_count,
        "total_tokens": run.total_tokens,
        "validity_status": "invalid_test_set",
        "invalid_reason": gate["reason"] or "invalid_test_set",
        "context_completeness": gate["context_completeness"],
        "analysis_warnings": gate["analysis_warnings"],
    }


def _mark_run_invalid_context(run: TestRun, gate: dict) -> None:
    context = gate.get("context_completeness") or {}
    missing = ", ".join(context.get("missing_targets") or [])
    run.status = "failed"
    run.stage = None
    run.finished_at = _now()
    run.error_code = "context_incomplete_blocking"
    run.error_message = f"target source context is incomplete: {missing or 'no source snippets'}"


def _resolve_temperature(default: float | None, override: dict | None, repeat_index: int) -> float | None:
    policy = ((override or {}).get("temperature_policy") or {}) if override else {}
    mode = policy.get("mode", "strategy_default")
    if mode == "fixed":
        return policy.get("value")
    if mode == "repeat_jitter" and policy.get("value") is not None:
        seed = int(policy.get("seed") or 0)
        return max(0.0, float(policy["value"]) + ((seed + repeat_index) % 3 - 1) * 0.01)
    return default


def create_experiment(
    session: Session,
    *,
    name: str,
    dataset_id: str,
    strategy_version_ids: list[str],
    repeat_count: int,
    llm_override: LlmOverride | dict | None = None,
    experiment_id: str | None = None,
) -> dict:
    if session.get(EvalDataset, dataset_id) is None:
        raise ExperimentNotFoundError("dataset not found")
    if experiment_id is not None and session.get(Experiment, experiment_id) is not None:
        raise ExperimentConflictError("experiment id already exists")
    for strategy_version_id in strategy_version_ids:
        if get_strategy_version(session, strategy_version_id) is None:
            raise ExperimentNotFoundError(f"strategy version not found: {strategy_version_id}")
    if len(set(strategy_version_ids)) != len(strategy_version_ids):
        raise ExperimentConflictError("strategy version ids must be unique")

    override_payload = None
    if llm_override is not None:
        override_payload = (
            llm_override.model_dump(exclude_none=True)
            if isinstance(llm_override, LlmOverride)
            else LlmOverride.model_validate(llm_override).model_dump(exclude_none=True)
        )

    experiment = Experiment(
        id=experiment_id or f"exp-{new_id()}",
        name=name,
        dataset_id=dataset_id,
        repeat_count=repeat_count,
        llm_override=override_payload,
        status="draft",
    )
    session.add(experiment)
    for index, strategy_version_id in enumerate(strategy_version_ids):
        session.add(
            ExperimentStrategyVersion(
                experiment_id=experiment.id,
                strategy_version_id=strategy_version_id,
                index=index,
            )
        )
    session.commit()
    session.refresh(experiment)
    return _serialize_experiment(session, experiment)


def list_experiments(session: Session) -> list[dict]:
    stmt = select(Experiment).order_by(Experiment.created_at.desc(), Experiment.id.asc())
    return [_serialize_experiment(session, experiment) for experiment in session.scalars(stmt)]


def get_experiment(session: Session, experiment_id: str) -> dict:
    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        raise ExperimentNotFoundError("experiment not found")
    return _serialize_experiment(session, experiment)


def cancel_experiment(session: Session, experiment_id: str) -> dict:
    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        raise ExperimentNotFoundError("experiment not found")
    if experiment.status not in {"completed", "failed", "cancelled"}:
        experiment.status = "cancelled"
        experiment.finished_at = _now()
        session.commit()
        session.refresh(experiment)
    return _serialize_experiment(session, experiment)


def enqueue_experiment(session: Session, experiment_id: str) -> dict:
    from app.workers.tasks import execute_experiment_task

    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        raise ExperimentNotFoundError("experiment not found")
    if experiment.status == "draft":
        experiment.status = "queued"
        experiment.started_at = None
        experiment.finished_at = None
        experiment.error_code = None
        experiment.error_message = None
        session.commit()
        execute_experiment_task.delay(experiment.id)
        session.refresh(experiment)
        return _serialize_experiment(session, experiment)
    if experiment.status in {"queued", "running", "completed", "cancelled"}:
        return _serialize_experiment(session, experiment)
    raise ExperimentConflictError("failed experiment cannot be rerun in place; create a new experiment")


def _dataset_tasks(session: Session, dataset_id: str) -> list[EvalTask]:
    stmt = select(EvalTask).where(EvalTask.dataset_id == dataset_id).order_by(EvalTask.created_at.asc(), EvalTask.id.asc())
    return list(session.scalars(stmt))


def _task_bugs_and_variants(session: Session, task_id: str) -> list[tuple[SeededBug, BugVariant]]:
    stmt = (
        select(SeededBug, BugVariant)
        .join(BugVariant, BugVariant.seeded_bug_id == SeededBug.id)
        .where(SeededBug.eval_task_id == task_id)
        .order_by(SeededBug.created_at.asc(), SeededBug.id.asc(), BugVariant.created_at.asc(), BugVariant.id.asc())
    )
    return list(session.execute(stmt).all())


def _raise_if_cancelled(session: Session, experiment_id: str) -> None:
    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        raise ExperimentNotFoundError("experiment not found")
    session.refresh(experiment)
    if experiment.status == "cancelled":
        raise ExperimentCancelledError("experiment cancelled")


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


def _final_test_set_from_db(session: Session, run_id: str) -> FinalTestSet:
    final_ids = _final_attempt_ids(session, run_id)
    files: dict[str, str] = {}
    for file in session.scalars(select(GeneratedTestFile).where(GeneratedTestFile.attempt_id.in_(final_ids))):
        files[file.path] = file.content_text or ""

    passed: set[str] = set()
    final_passed = final_failed = final_skipped = collection_errors = n_cases = 0
    clean_failed = False
    for result in session.scalars(select(PytestCaseResult).where(PytestCaseResult.attempt_id.in_(final_ids))):
        if result.is_collection_error:
            collection_errors += 1
            clean_failed = True
            continue
        n_cases += 1
        if result.status == "passed":
            final_passed += 1
            passed.add(result.nodeid)
        elif result.status == "skipped":
            final_skipped += 1
        elif result.status in {"failed", "error"}:
            final_failed += 1
            clean_failed = True
    return FinalTestSet(
        files=files,
        clean_passed=passed,
        clean_failed=clean_failed,
        n_cases=n_cases,
        collection_errors=collection_errors,
        final_passed=final_passed,
        final_failed=final_failed,
        final_skipped=final_skipped,
    )


def _artifact_dir(run_id: str) -> Path:
    path = EXPERIMENT_WORK_ROOT / "artifacts" / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _store_generated_test_set_artifact(
    session: Session,
    *,
    run_id: str,
    experiment_id: str,
    clean_run_id: str,
    final_set: FinalTestSet,
) -> RunArtifact:
    payload = {"files": final_set.files}
    data = _json_bytes(payload)
    content_hash = _sha256_bytes(data)
    artifact_id = new_id()
    path = _artifact_dir(run_id) / f"{artifact_id}.generated_test_set.json"
    path.write_bytes(data)
    artifact = RunArtifact(
        id=artifact_id,
        run_id=run_id,
        attempt_id=None,
        artifact_type="generated_test_set",
        uri=str(path),
        content_hash=content_hash,
        size_bytes=len(data),
        metadata_json={
            "kind": "generated_test_set",
            "created_by": "experiment_service",
            "experiment_id": experiment_id,
            "clean_run_id": clean_run_id,
            "content_role": "final_clean_test_set",
            "relative_paths": sorted(final_set.files),
            "hash_algorithm": "sha256",
        },
    )
    session.add(artifact)
    session.commit()
    session.refresh(artifact)
    return artifact


def _read_generated_test_set_artifact(artifact: RunArtifact) -> dict[str, str]:
    path = Path(artifact.uri)
    data = path.read_bytes()
    if artifact.content_hash and _sha256_bytes(data) != artifact.content_hash:
        raise ExperimentError("generated test set artifact hash mismatch")
    payload = json.loads(data.decode("utf-8"))
    return {str(k): str(v) for k, v in dict(payload.get("files") or {}).items()}


def _copy_clean_snapshot(snapshot: ProjectSnapshot, dest: Path) -> Path:
    root = Path(snapshot.root_path).resolve()
    dest = _ensure_experiment_work_path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(
        root,
        dest,
        ignore=shutil.ignore_patterns(
            ".trace_artifacts",
            ".trace_junit.xml",
            ".trace_pytest_report.json",
            ".pytest_cache",
            "__pycache__",
        ),
    )
    return dest


def _materialize_clean_snapshot(session: Session, *, source_snapshot: ProjectSnapshot, experiment_id: str, unit: str) -> ProjectSnapshot:
    experiment_segment = _safe_path_segment(experiment_id, label="experiment_id")
    unit_segment = _safe_path_segment(unit, label="experiment unit")
    root = _copy_clean_snapshot(
        source_snapshot,
        EXPERIMENT_WORK_ROOT / experiment_segment / unit_segment / "clean",
    )
    content_hash = _hash_directory(root)
    snapshot = ProjectSnapshot(
        id=new_id(),
        project_id=source_snapshot.project_id,
        source_kind="experiment_clean_materialized",
        root_path=str(root),
        content_hash=content_hash,
    )
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def _hash_directory(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(".trace_artifacts/") or rel in {".trace_pytest_report.json", ".trace_junit.xml"}:
            continue
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _apply_inline_patch(root: Path, variant: BugVariant) -> None:
    patch = ((variant.ground_truth or {}).get("patch_artifact") or {}).get("patch") or {}
    file = patch.get("file")
    old = patch.get("old")
    new = patch.get("new", "")
    if not file or old is None:
        raise ExperimentError(f"bug variant {variant.id} has no inline canonical patch")
    target = (root / file).resolve()
    if root.resolve() not in target.parents and target != root.resolve():
        raise ExperimentError("bug patch target escapes variant root")
    text = target.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise ExperimentError(f"bug variant {variant.id} canonical patch must hit exactly once during replay")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def _check_variant_probe(*, clean_root: Path, variant_root: Path, variant: BugVariant) -> dict | None:
    try:
        return check_variant_probe(
            clean_root=clean_root,
            variant_root=variant_root,
            ground_truth=variant.ground_truth or {},
            variant_id=variant.id,
        )
    except ProbeCheckError as exc:
        raise ExperimentError(str(exc)) from exc


def _pytest_summary_from_replay(out) -> dict:
    return {
        "collected": out.collected,
        "passed": out.passed,
        "failed": out.failed,
        "skipped": out.skipped,
        "collection_errors": len(out.collection_errors),
        "duration_ms": out.duration_ms,
        "exit_code": out.exit_code,
        "error": out.error,
        "case_results": [case.model_dump() for case in out.case_results],
        "failures": [failure.model_dump() for failure in out.failures],
    }


def _passed_nodeids_from_pytest_summary(summary: dict) -> set[str]:
    return {
        str(case.get("nodeid"))
        for case in summary.get("case_results", [])
        if isinstance(case, dict) and case.get("status") == "passed" and case.get("nodeid")
    }


def _nodeid_statuses_from_pytest_summary(summary: dict) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for case in summary.get("case_results", []):
        if isinstance(case, dict) and case.get("nodeid"):
            statuses[str(case["nodeid"])] = str(case.get("status") or "unknown")
    return statuses


def _compact_pytest_summary(summary: dict) -> dict:
    return {
        "collected": int(summary.get("collected", 0)),
        "passed": int(summary.get("passed", 0)),
        "failed": int(summary.get("failed", 0)),
        "skipped": int(summary.get("skipped", 0)),
        "collection_errors": int(summary.get("collection_errors", 0)),
        "duration_ms": int(summary.get("duration_ms") or 0),
        "exit_code": summary.get("exit_code"),
        "error": summary.get("error"),
    }


def _replay_timeout_seconds(runtime_snapshot: dict | None, *, default: int = DEFAULT_REPLAY_TIMEOUT_SECONDS) -> int:
    snapshot = runtime_snapshot or {}
    for candidate in (
        snapshot.get("timeout_seconds"),
        (snapshot.get("budget_override") or {}).get("timeout_seconds") if isinstance(snapshot.get("budget_override"), dict) else None,
    ):
        if candidate is None:
            continue
        try:
            return max(1, int(candidate))
        except (TypeError, ValueError):
            continue
    return default


def _flaky_mismatch_reason(expected: dict[str, str], actual: dict[str, str]) -> str | None:
    if set(expected) != set(actual):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        parts = []
        if missing:
            parts.append("missing nodeids: " + ", ".join(missing))
        if extra:
            parts.append("extra nodeids: " + ", ".join(extra))
        return "; ".join(parts)
    changed = sorted(nodeid for nodeid in expected if expected[nodeid] != actual[nodeid])
    if changed:
        return "status changed: " + ", ".join(
            f"{nodeid} {expected[nodeid]}->{actual[nodeid]}" for nodeid in changed
        )
    return None


def _run_clean_flaky_gate(
    session: Session,
    *,
    clean_run: ExperimentCleanRun,
    artifact: RunArtifact,
    target_snapshot: ProjectSnapshot,
    baseline_replay: TestReplay,
    baseline_statuses: dict[str, str],
    timeout_seconds: int,
    required_runs: int = FLAKY_CLEAN_REPLAY_RUNS,
) -> dict:
    replay_ids = [baseline_replay.id]
    runs = [
        {
            "replay_id": baseline_replay.id,
            "summary": _compact_pytest_summary(baseline_replay.pytest_summary or {}),
            "nodeid_statuses": baseline_statuses,
        }
    ]
    stable = True
    reasons: list[str] = []

    for index in range(1, required_runs):
        replay_row, _capturing, _assertion_failures = _run_replay(
            session,
            clean_run=clean_run,
            artifact=artifact,
            target_snapshot=target_snapshot,
            variant=None,
            clean_passed=set(),
            timeout_seconds=timeout_seconds,
        )
        replay_ids.append(replay_row.id)
        statuses = _nodeid_statuses_from_pytest_summary(replay_row.pytest_summary or {})
        summary = _compact_pytest_summary(replay_row.pytest_summary or {})
        runs.append(
            {
                "replay_id": replay_row.id,
                "summary": summary,
                "nodeid_statuses": statuses,
            }
        )
        mismatch = _flaky_mismatch_reason(baseline_statuses, statuses)
        if replay_row.status != "completed":
            stable = False
            reasons.append(f"run {index + 1} failed: {replay_row.error_message or replay_row.error_code}")
        if summary["collection_errors"] > 0:
            stable = False
            reasons.append(f"run {index + 1} had collection errors")
        if mismatch:
            stable = False
            reasons.append(f"run {index + 1} mismatch: {mismatch}")

    return {
        "enabled": True,
        "required_runs": required_runs,
        "actual_runs": len(replay_ids),
        "stable": stable,
        "baseline_replay_id": baseline_replay.id,
        "replay_ids": replay_ids,
        "reasons": reasons,
        "runs": runs,
    }


def _run_replay(
    session: Session,
    *,
    clean_run: ExperimentCleanRun,
    artifact: RunArtifact,
    target_snapshot: ProjectSnapshot,
    variant: BugVariant | None,
    clean_passed: set[str],
    timeout_seconds: int,
) -> tuple[TestReplay, list[str], list[str]]:
    replay_id = new_id()
    replay_row = TestReplay(
        id=replay_id,
        experiment_clean_run_id=clean_run.id,
        generated_test_set_artifact_id=artifact.id,
        target_snapshot_id=target_snapshot.id,
        bug_variant_id=variant.id if variant is not None else None,
        status="running",
        pytest_summary={},
        replay_mode="frozen_test_set",
        llm_calls=0,
        started_at=_now(),
    )
    session.add(replay_row)
    session.commit()

    try:
        files = _read_generated_test_set_artifact(artifact)
        experiment_segment = _safe_path_segment(clean_run.experiment_id, label="experiment_id")
        clean_segment = _safe_path_segment(clean_run.id, label="experiment_clean_run_id")
        replay_segment = _safe_path_segment(replay_id, label="replay_id")
        replay_root = _copy_clean_snapshot(
            target_snapshot,
            EXPERIMENT_WORK_ROOT / experiment_segment / clean_segment / f"replay-{replay_segment}",
        )
        probe_check = None
        if variant is not None:
            _apply_inline_patch(replay_root, variant)
            probe_check = _check_variant_probe(
                clean_root=Path(target_snapshot.root_path),
                variant_root=replay_root,
                variant=variant,
            )
        out = replay_frozen_tests(replay_root, files, timeout_seconds=timeout_seconds)
        summary = _pytest_summary_from_replay(out)
        if probe_check is not None:
            summary["probe_check"] = probe_check
        assertion_failures = [
            case.nodeid
            for case in out.case_results
            if case.status == "failed" and case.failure_type == "assertion"
        ]
        capturing = [nodeid for nodeid in assertion_failures if nodeid in clean_passed]
        replay_row.status = "completed" if out.error is None else "failed"
        replay_row.pytest_summary = summary
        replay_row.error_code = "PYTEST_REPLAY_ERROR" if out.error else None
        replay_row.error_message = out.error
        replay_row.finished_at = _now()
        session.commit()
        session.refresh(replay_row)
        return replay_row, capturing, assertion_failures
    except Exception as exc:
        replay_row.status = "failed"
        replay_row.error_code = type(exc).__name__
        replay_row.error_message = str(exc)
        replay_row.finished_at = _now()
        session.commit()
        raise


def _make_llm_for_strategy(provider: str):
    if provider == "mock":
        return lambda: MockLLM(demo_author)
    return None


def _experiment_event_projection_inputs(
    session: Session,
    experiment_id: str,
) -> tuple[list[ExperimentCleanRun], list[TestReplay], list[ExperimentReplayRun]]:
    clean_runs = list(
        session.scalars(
            select(ExperimentCleanRun)
            .where(ExperimentCleanRun.experiment_id == experiment_id)
            .order_by(ExperimentCleanRun.created_at.asc(), ExperimentCleanRun.id.asc())
        )
    )
    replays = list(
        session.scalars(
            select(TestReplay)
            .join_from(TestReplay, ExperimentCleanRun)
            .where(ExperimentCleanRun.experiment_id == experiment_id)
            .order_by(TestReplay.created_at.asc(), TestReplay.id.asc())
        )
    )
    replay_results = list(
        session.scalars(
            select(ExperimentReplayRun)
            .join_from(ExperimentReplayRun, ExperimentCleanRun)
            .where(ExperimentCleanRun.experiment_id == experiment_id)
            .order_by(ExperimentReplayRun.created_at.asc(), ExperimentReplayRun.id.asc())
        )
    )
    return clean_runs, replays, replay_results


def _reflection_event_backfeed_for_unit(
    session: Session,
    experiment: Experiment,
    *,
    eval_task_id: str,
    strategy_version_id: str,
    repeat_index: int,
) -> list[EvaluationEventContract]:
    clean_runs, replays, replay_results = _experiment_event_projection_inputs(session, experiment.id)
    projected = project_evaluation_events(experiment, clean_runs, replays, replay_results)
    return build_reflection_event_backfeed(
        projected,
        eval_task_id=eval_task_id,
        strategy_version_id=strategy_version_id,
        before_repeat_index=repeat_index,
    ).events


def run_experiment(session: Session, experiment_id: str) -> dict:
    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        raise ExperimentNotFoundError("experiment not found")
    if experiment.status in {"completed", "cancelled"}:
        return _serialize_experiment(session, experiment)
    if experiment.status == "failed":
        raise ExperimentConflictError("failed experiment cannot be rerun in place; create a new experiment")

    tasks = _dataset_tasks(session, experiment.dataset_id)
    if not tasks:
        raise ExperimentError("experiment dataset has no eval tasks")
    strategy_ids = _experiment_strategy_ids(session, experiment.id)
    if not strategy_ids:
        raise ExperimentError("experiment has no strategy versions")

    experiment.status = "running"
    experiment.started_at = _now()
    experiment.finished_at = None
    experiment.error_code = None
    experiment.error_message = None
    session.commit()

    try:
        for task in tasks:
            _raise_if_cancelled(session, experiment.id)
            snapshot = session.get(ProjectSnapshot, task.project_snapshot_id)
            if snapshot is None:
                raise ExperimentError("eval task project snapshot not found")
            variants = _task_bugs_and_variants(session, task.id)
            for strategy_version_id in strategy_ids:
                _raise_if_cancelled(session, experiment.id)
                strategy = get_strategy_version(session, strategy_version_id)
                if strategy is None:
                    raise ExperimentError(f"strategy version not found: {strategy_version_id}")
                for repeat_index in range(experiment.repeat_count):
                    _raise_if_cancelled(session, experiment.id)
                    unit = f"{task.id}-{strategy_version_id}-rep{repeat_index}"
                    clean_snapshot = _materialize_clean_snapshot(
                        session,
                        source_snapshot=snapshot,
                        experiment_id=experiment.id,
                        unit=unit,
                    )
                    task_targets = _task_targets(task)
                    plan = create_test_plan(
                        session,
                        project_id=clean_snapshot.project_id,
                        name=f"{experiment.name} / {task.id} / {strategy_version_id} / rep{repeat_index}",
                        target_scope=task_targets,
                        goal=task.goal,
                        budget={"allow_reflection": strategy.allow_reflection, "timeout_seconds": 120},
                        output_options={"experiment_id": experiment.id, "eval_task_id": task.id},
                        default_strategy_version_id=strategy_version_id,
                    )
                    override = experiment.llm_override or {}
                    temperature = _resolve_temperature(strategy.temperature, override, repeat_index)
                    run = create_run(
                        session,
                        plan_id=plan.id,
                        snapshot_id=clean_snapshot.id,
                        strategy_version_id=strategy_version_id,
                        llm_provider=override.get("provider"),
                        llm_model=override.get("model"),
                        llm_temperature=temperature,
                        llm_max_output_tokens=override.get("max_output_tokens"),
                        llm_model_params=dict(override.get("model_params") or {}),
                        llm_repeat_index=repeat_index,
                        budget_override={"allow_reflection": strategy.allow_reflection, "timeout_seconds": 120},
                        output_options={"experiment_id": experiment.id, "eval_task_id": task.id},
                    )
                    session.refresh(run)
                    _raise_if_cancelled(session, experiment.id)
                    gate = _context_gate(clean_snapshot, task_targets)
                    if gate["blocking"]:
                        _mark_run_invalid_context(run, gate)
                        clean_id = new_id()
                        artifact = _store_generated_test_set_artifact(
                            session,
                            run_id=run.id,
                            experiment_id=experiment.id,
                            clean_run_id=clean_id,
                            final_set=_empty_final_test_set(),
                        )
                        clean_row = ExperimentCleanRun(
                            id=clean_id,
                            experiment_id=experiment.id,
                            eval_task_id=task.id,
                            strategy_version_id=strategy_version_id,
                            repeat_index=repeat_index,
                            clean_run_id=run.id,
                            generated_test_set_artifact_id=artifact.id,
                            false_positive=False,
                            clean_metrics=_invalid_clean_metrics(run, gate),
                        )
                        session.add(clean_row)
                        session.commit()
                        continue
                    provider = ((run.strategy_snapshot or {}).get("resolved_llm") or {}).get("provider", "mock")
                    evaluation_events = _reflection_event_backfeed_for_unit(
                        session,
                        experiment,
                        eval_task_id=task.id,
                        strategy_version_id=strategy_version_id,
                        repeat_index=repeat_index,
                    )
                    execute_run_sync(
                        session,
                        run_id=run.id,
                        make_llm=_make_llm_for_strategy(provider),
                        evaluation_events=evaluation_events,
                    )
                    session.refresh(run)
                    _raise_if_cancelled(session, experiment.id)
                    if run.status != "completed":
                        if run.error_code == "PIPELINE_REJECT":
                            clean_id = new_id()
                            artifact = _store_generated_test_set_artifact(
                                session,
                                run_id=run.id,
                                experiment_id=experiment.id,
                                clean_run_id=clean_id,
                                final_set=_empty_final_test_set(),
                            )
                            clean_row = ExperimentCleanRun(
                                id=clean_id,
                                experiment_id=experiment.id,
                                eval_task_id=task.id,
                                strategy_version_id=strategy_version_id,
                                repeat_index=repeat_index,
                                clean_run_id=run.id,
                                generated_test_set_artifact_id=artifact.id,
                                false_positive=False,
                                clean_metrics={
                                    "final_cases_total": 0,
                                    "final_passed": 0,
                                    "final_failed": 0,
                                    "final_skipped": 0,
                                    "collection_errors": 0,
                                    "tool_call_count": run.tool_call_count,
                                    "total_tokens": run.total_tokens,
                                    "validity_status": "invalid_test_set",
                                    "invalid_reason": "pipeline_reject",
                                    "pipeline_reject_error": run.error_message,
                                },
                            )
                            session.add(clean_row)
                            session.commit()
                            continue
                        detail = run.error_code or run.status
                        if run.error_message:
                            detail = f"{detail}: {run.error_message}"
                        raise ExperimentError(f"clean run failed before replay: {detail}")
                    final_set = _final_test_set_from_db(session, run.id)
                    clean_metrics = {
                        "final_cases_total": final_set.n_cases,
                        "final_passed": final_set.final_passed,
                        "final_failed": final_set.final_failed,
                        "final_skipped": final_set.final_skipped,
                        "collection_errors": final_set.collection_errors,
                        "tool_call_count": run.tool_call_count,
                        "total_tokens": run.total_tokens,
                        "validity_status": "evaluable",
                    }
                    clean_id = new_id()
                    artifact = _store_generated_test_set_artifact(
                        session,
                        run_id=run.id,
                        experiment_id=experiment.id,
                        clean_run_id=clean_id,
                        final_set=final_set,
                    )
                    clean_row = ExperimentCleanRun(
                        id=clean_id,
                        experiment_id=experiment.id,
                        eval_task_id=task.id,
                        strategy_version_id=strategy_version_id,
                        repeat_index=repeat_index,
                        clean_run_id=run.id,
                        generated_test_set_artifact_id=artifact.id,
                        false_positive=final_set.clean_failed,
                        clean_metrics=clean_metrics,
                    )
                    session.add(clean_row)
                    session.commit()
                    session.refresh(clean_row)

                    replay_timeout_seconds = _replay_timeout_seconds(run.runtime_snapshot)
                    clean_replay_row, _clean_capturing, clean_assertion_failures = _run_replay(
                        session,
                        clean_run=clean_row,
                        artifact=artifact,
                        target_snapshot=snapshot,
                        variant=None,
                        clean_passed=final_set.clean_passed,
                        timeout_seconds=replay_timeout_seconds,
                    )
                    clean_replay_summary = _compact_pytest_summary(clean_replay_row.pytest_summary or {})
                    clean_metrics = dict(clean_row.clean_metrics or {})
                    clean_metrics["clean_replay_id"] = clean_replay_row.id
                    clean_metrics["clean_replay"] = clean_replay_summary
                    clean_metrics["clean_replay_assertion_failure_nodeids"] = sorted(clean_assertion_failures)

                    if clean_replay_row.status != "completed":
                        # clean 测试集在干净代码上无法复现：这一个 (task, strategy, repeat) 单元作废，
                        # 记为失败并跳过它的变体重放。环境抖动只废掉这个单元，不连累整场实验——
                        # 其它策略/重复仍继续。真正的系统级损坏（artifact hash 不符、拷贝失败）由
                        # _run_replay 抛异常走外层 except，仍会让实验失败。
                        clean_metrics["clean_replay_error"] = clean_replay_row.error_message or clean_replay_row.error_code
                        clean_metrics["clean_replay_matches_generation"] = False
                        clean_metrics["validity_status"] = "invalid_test_set"
                        clean_metrics["invalid_reason"] = "clean_replay_failed"
                        clean_row.false_positive = False
                        clean_row.clean_metrics = clean_metrics
                        session.commit()
                        continue

                    clean_replay_passed = _passed_nodeids_from_pytest_summary(clean_replay_row.pytest_summary or {})
                    clean_replay_statuses = _nodeid_statuses_from_pytest_summary(clean_replay_row.pytest_summary or {})
                    if clean_replay_summary["collection_errors"] > 0:
                        clean_metrics["clean_replay_matches_generation"] = False
                        clean_metrics["validity_status"] = "invalid_test_set"
                        clean_metrics["invalid_reason"] = "clean_replay_collection_error"
                        clean_row.false_positive = False
                        clean_row.clean_metrics = clean_metrics
                        session.commit()
                        continue

                    flaky_check = _run_clean_flaky_gate(
                        session,
                        clean_run=clean_row,
                        artifact=artifact,
                        target_snapshot=snapshot,
                        baseline_replay=clean_replay_row,
                        baseline_statuses=clean_replay_statuses,
                        timeout_seconds=replay_timeout_seconds,
                    )
                    clean_metrics["flaky_check"] = flaky_check
                    if not flaky_check["stable"]:
                        clean_metrics["validity_status"] = "invalid_test_set"
                        clean_metrics["invalid_reason"] = "flaky_clean_replay"
                        clean_row.false_positive = False
                        clean_row.clean_metrics = clean_metrics
                        session.commit()
                        continue

                    clean_replay_failed = bool(clean_assertion_failures)
                    clean_row.false_positive = clean_replay_failed
                    clean_metrics["clean_replay_matches_generation"] = (
                        clean_replay_summary["passed"] == final_set.final_passed
                        and clean_replay_summary["failed"] == final_set.final_failed
                        and clean_replay_summary["skipped"] == final_set.final_skipped
                        and clean_replay_summary["collection_errors"] == final_set.collection_errors
                    )
                    clean_row.clean_metrics = clean_metrics
                    session.commit()

                    for _bug, variant in variants:
                        _raise_if_cancelled(session, experiment.id)
                        replay_row, capturing, assertion_failures = _run_replay(
                            session,
                            clean_run=clean_row,
                            artifact=artifact,
                            target_snapshot=snapshot,
                            variant=variant,
                            clean_passed=clean_replay_passed,
                            timeout_seconds=replay_timeout_seconds,
                        )
                        session.add(
                            ExperimentReplayRun(
                                id=new_id(),
                                experiment_clean_run_id=clean_row.id,
                                bug_variant_id=variant.id,
                                replay_id=replay_row.id,
                                captured_bug=bool(capturing),
                                replay_metrics={
                                    "capture_rule": "clean_passed_variant_assertion_failure_same_nodeid",
                                    "clean_passed_nodeids": sorted(clean_replay_passed),
                                    "variant_assertion_failure_nodeids": sorted(assertion_failures),
                                    "capturing_nodeids": sorted(capturing),
                                    "clean_replay_id": clean_replay_row.id,
                                    "probe_check": (replay_row.pytest_summary or {}).get("probe_check"),
                                },
                            )
                        )
                        session.commit()

        experiment.status = "completed"
        experiment.finished_at = _now()
        session.commit()
    except ExperimentCancelledError:
        session.rollback()
        experiment = session.get(Experiment, experiment_id)
        if experiment is not None:
            experiment.status = "cancelled"
            experiment.finished_at = experiment.finished_at or _now()
            session.commit()
            session.refresh(experiment)
            return _serialize_experiment(session, experiment)
        raise
    except Exception as exc:
        session.rollback()
        experiment = session.get(Experiment, experiment_id)
        if experiment is not None:
            experiment.status = "failed"
            experiment.finished_at = _now()
            experiment.error_code = type(exc).__name__
            experiment.error_message = str(exc)
            session.commit()
        raise

    refreshed = session.get(Experiment, experiment_id)
    assert refreshed is not None
    return _serialize_experiment(session, refreshed)


def list_clean_runs(session: Session, experiment_id: str) -> list[ExperimentCleanRun]:
    if session.get(Experiment, experiment_id) is None:
        raise ExperimentNotFoundError("experiment not found")
    stmt = (
        select(ExperimentCleanRun)
        .where(ExperimentCleanRun.experiment_id == experiment_id)
        .order_by(ExperimentCleanRun.created_at.asc(), ExperimentCleanRun.id.asc())
    )
    return list(session.scalars(stmt))


def list_replay_runs(session: Session, experiment_id: str) -> list[TestReplay]:
    if session.get(Experiment, experiment_id) is None:
        raise ExperimentNotFoundError("experiment not found")
    stmt = (
        select(TestReplay)
        .join_from(TestReplay, ExperimentCleanRun)
        .where(ExperimentCleanRun.experiment_id == experiment_id)
        .order_by(TestReplay.created_at.asc(), TestReplay.id.asc())
    )
    return list(session.scalars(stmt))


def get_experiment_metrics(session: Session, experiment_id: str) -> dict:
    from app.services.experiment_metrics import get_experiment_metrics as _get_experiment_metrics

    try:
        return _get_experiment_metrics(session, experiment_id)
    except EvaluationNotFoundError as exc:
        raise ExperimentNotFoundError(str(exc)) from exc
