from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

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
    Strategy,
    TestReplay,
    TestReport,
    TestRun,
)
from app.repositories.strategies import get_strategy_version
from app.schemas.evaluation import LlmOverride
from app.services.evaluation import EvaluationConflictError, EvaluationError, EvaluationNotFoundError
from app.services.test_plans import create_test_plan
from app.services.test_runs import create_run, execute_run_sync
from eval.harness import metrics as harness_metrics
from eval.harness.authors import demo_author
from eval.harness.replay import replay as replay_frozen_tests

TRACE_ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_WORK_ROOT = TRACE_ROOT / ".pytest_tmp_experiments"


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
    variants: dict = field(default_factory=dict)


class ExperimentError(EvaluationError):
    pass


class ExperimentNotFoundError(EvaluationNotFoundError):
    pass


class ExperimentConflictError(EvaluationConflictError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _experiment_strategy_ids(session: Session, experiment_id: str) -> list[str]:
    stmt = (
        select(ExperimentStrategyVersion)
        .where(ExperimentStrategyVersion.experiment_id == experiment_id)
        .order_by(ExperimentStrategyVersion.index.asc())
    )
    return [row.strategy_version_id for row in session.scalars(stmt)]


def _strategy_name(session: Session, strategy_version_id: str) -> str:
    sv = get_strategy_version(session, strategy_version_id)
    return sv.name if sv is not None else strategy_version_id


def _strategy_key(session: Session, strategy_version_id: str) -> str:
    sv = get_strategy_version(session, strategy_version_id)
    return (sv.strategy_id or sv.id) if sv is not None else strategy_version_id


def _strategy_parent_name(session: Session, strategy_version_id: str) -> str:
    sv = get_strategy_version(session, strategy_version_id)
    if sv is None:
        return strategy_version_id
    parent = session.get(Strategy, sv.strategy_id) if sv.strategy_id else None
    return parent.name if parent is not None else sv.name


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
    results_by_attempt: dict[str, list[PytestCaseResult]] = {}
    for result in results:
        results_by_attempt.setdefault(result.attempt_id, []).append(result)
    attempts_by_item: dict[str, list[RunAttempt]] = {}
    for attempt in attempts:
        attempts_by_item.setdefault(attempt.run_plan_item_id, []).append(attempt)
    final_ids = set()
    for item_attempts in attempts_by_item.values():
        with_results = [attempt for attempt in item_attempts if attempt.id in results_by_attempt]
        pool = with_results or item_attempts
        final_ids.add(max(pool, key=lambda attempt: attempt.attempt_no).id)
    return final_ids


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
    dest = dest.resolve()
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(root, dest)
    return dest


def _materialize_clean_snapshot(session: Session, *, source_snapshot: ProjectSnapshot, experiment_id: str, unit: str) -> ProjectSnapshot:
    root = _copy_clean_snapshot(
        source_snapshot,
        EXPERIMENT_WORK_ROOT / experiment_id / unit / "clean",
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
        replay_root = _copy_clean_snapshot(
            target_snapshot,
            EXPERIMENT_WORK_ROOT / clean_run.experiment_id / clean_run.id / f"replay-{replay_id}",
        )
        if variant is not None:
            _apply_inline_patch(replay_root, variant)
        out = replay_frozen_tests(replay_root, files, timeout_seconds=timeout_seconds)
        summary = _pytest_summary_from_replay(out)
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


def run_experiment(session: Session, experiment_id: str) -> dict:
    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        raise ExperimentNotFoundError("experiment not found")
    if experiment.status == "cancelled":
        return _serialize_experiment(session, experiment)

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
            snapshot = session.get(ProjectSnapshot, task.project_snapshot_id)
            if snapshot is None:
                raise ExperimentError("eval task project snapshot not found")
            variants = _task_bugs_and_variants(session, task.id)
            for strategy_version_id in strategy_ids:
                strategy = get_strategy_version(session, strategy_version_id)
                if strategy is None:
                    raise ExperimentError(f"strategy version not found: {strategy_version_id}")
                for repeat_index in range(experiment.repeat_count):
                    unit = f"{task.id}-{strategy_version_id}-rep{repeat_index}"
                    clean_snapshot = _materialize_clean_snapshot(
                        session,
                        source_snapshot=snapshot,
                        experiment_id=experiment.id,
                        unit=unit,
                    )
                    plan = create_test_plan(
                        session,
                        project_id=clean_snapshot.project_id,
                        name=f"{experiment.name} / {task.id} / {strategy_version_id} / rep{repeat_index}",
                        target_scope=_task_targets(task),
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
                    provider = ((run.strategy_snapshot or {}).get("resolved_llm") or {}).get("provider", "mock")
                    execute_run_sync(
                        session,
                        run_id=run.id,
                        make_llm=_make_llm_for_strategy(provider),
                    )
                    session.refresh(run)
                    final_set = _final_test_set_from_db(session, run.id)
                    clean_metrics = {
                        "final_cases_total": final_set.n_cases,
                        "final_passed": final_set.final_passed,
                        "final_failed": final_set.final_failed,
                        "final_skipped": final_set.final_skipped,
                        "collection_errors": final_set.collection_errors,
                        "tool_call_count": run.tool_call_count,
                        "total_tokens": run.total_tokens,
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

                    _run_replay(
                        session,
                        clean_run=clean_row,
                        artifact=artifact,
                        target_snapshot=snapshot,
                        variant=None,
                        clean_passed=final_set.clean_passed,
                        timeout_seconds=60,
                    )
                    for _bug, variant in variants:
                        replay_row, capturing, assertion_failures = _run_replay(
                            session,
                            clean_run=clean_row,
                            artifact=artifact,
                            target_snapshot=snapshot,
                            variant=variant,
                            clean_passed=final_set.clean_passed,
                            timeout_seconds=60,
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
                                    "clean_passed_nodeids": sorted(final_set.clean_passed),
                                    "variant_assertion_failure_nodeids": sorted(assertion_failures),
                                    "capturing_nodeids": sorted(capturing),
                                },
                            )
                        )
                        session.commit()

        experiment.status = "completed"
        experiment.finished_at = _now()
        session.commit()
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


def _metric_runs(session: Session, experiment_id: str) -> dict[str, list[MetricRun]]:
    stmt = (
        select(ExperimentCleanRun)
        .where(ExperimentCleanRun.experiment_id == experiment_id)
        .order_by(ExperimentCleanRun.strategy_version_id.asc(), ExperimentCleanRun.repeat_index.asc())
    )
    runs_by_strategy: dict[str, list[MetricRun]] = {}
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
        metric_run = MetricRun(
            strategy_id=sid,
            strategy_name=_strategy_parent_name(session, clean.strategy_version_id),
            repeat=clean.repeat_index,
            status=run.status if run is not None else "unknown",
            clean_passed=set(),
            clean_failed=clean.false_positive,
            n_cases=int((clean.clean_metrics or {}).get("final_cases_total", 0)),
            tokens=int((clean.clean_metrics or {}).get("total_tokens", 0)),
            tool_calls=int((clean.clean_metrics or {}).get("tool_call_count", 0)),
            reflection_used=bool(metrics.get("reflection_used")),
            variants=variants,
        )
        runs_by_strategy.setdefault(sid, []).append(metric_run)
    return runs_by_strategy


def _capture_matrix_variant_ids(session: Session, experiment: Experiment) -> list[str]:
    stmt = (
        select(BugVariant.id)
        .join_from(BugVariant, SeededBug)
        .join_from(SeededBug, EvalTask)
        .where(EvalTask.dataset_id == experiment.dataset_id)
        .order_by(SeededBug.created_at.asc(), SeededBug.id.asc(), BugVariant.created_at.asc(), BugVariant.id.asc())
    )
    return [row for row in session.scalars(stmt)]


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


def get_experiment_metrics(session: Session, experiment_id: str) -> dict:
    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        raise ExperimentNotFoundError("experiment not found")
    runs_by_strategy = _metric_runs(session, experiment_id)
    total_in_scope = len(_capture_matrix_variant_ids(session, experiment))
    rows = harness_metrics.aggregate(runs_by_strategy, total_in_scope=total_in_scope)

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
    matrix = {
        variant_id: {
            strategy_id: any(run.variants.get(variant_id, {}).get("captured") for run in runs)
            for strategy_id, runs in runs_by_strategy.items()
        }
        for variant_id in variant_ids
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
    artifacts = list(
        session.scalars(
            select(RunArtifact)
            .where(RunArtifact.artifact_type == "generated_test_set")
            .order_by(RunArtifact.created_at.asc(), RunArtifact.id.asc())
        )
    )
    artifacts = [
        artifact
        for artifact in artifacts
        if (artifact.metadata_json or {}).get("experiment_id") == experiment_id
    ]

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
        "rows": rows,
        "capture_matrix": matrix,
        "clean_runs": [
            {
                "id": clean.id,
                "experiment_id": clean.experiment_id,
                "eval_task_id": clean.eval_task_id,
                "strategy_version_id": clean.strategy_version_id,
                "repeat_index": clean.repeat_index,
                "clean_run_id": clean.clean_run_id,
                "generated_test_set_artifact_id": clean.generated_test_set_artifact_id,
                "false_positive": clean.false_positive,
                "clean_metrics": clean.clean_metrics,
                "runtime_snapshot": (session.get(TestRun, clean.clean_run_id).runtime_snapshot or {}),
                "strategy_snapshot": (session.get(TestRun, clean.clean_run_id).strategy_snapshot or {}),
                "report_quality": ((session.scalar(select(TestReport).where(TestReport.run_id == clean.clean_run_id))).metrics or {}).get("report_quality", {}),
            }
            for clean in clean_runs
        ],
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
