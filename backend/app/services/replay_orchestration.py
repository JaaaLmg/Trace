from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Type

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.models import BugVariant, ExperimentReplayRun, SeededBug
from app.services.replay_scheduler import ReplayJobResult


@dataclass(frozen=True)
class VariantReplayJob:
    clean_run_id: str
    artifact_id: str
    target_snapshot_id: str
    variant_id: str
    clean_passed: set[str]
    timeout_seconds: int


@dataclass(frozen=True)
class CleanReplayJob:
    clean_run_id: str
    artifact_id: str
    target_snapshot_id: str
    timeout_seconds: int


@dataclass(frozen=True)
class FlakyGateReplayJob:
    clean_run_id: str
    artifact_id: str
    target_snapshot_id: str
    baseline_replay_id: str
    baseline_statuses: dict[str, str]
    required_runs: int
    timeout_seconds: int


@dataclass(frozen=True)
class ProbeCheckJob:
    clean_snapshot_root: str
    variant_snapshot_root: str
    variant_id: str


@dataclass(frozen=True)
class VariantReplayJobOutput:
    replay_id: str
    bug_variant_id: str
    captured_bug: bool
    replay_metrics: dict


def build_variant_replay_jobs(
    *,
    clean_run_id: str,
    artifact_id: str,
    target_snapshot_id: str,
    variants: Iterable[tuple[SeededBug, BugVariant]],
    clean_passed: set[str],
    timeout_seconds: int,
) -> list[VariantReplayJob]:
    return [
        VariantReplayJob(
            clean_run_id=clean_run_id,
            artifact_id=artifact_id,
            target_snapshot_id=target_snapshot_id,
            variant_id=variant.id,
            clean_passed=set(clean_passed),
            timeout_seconds=timeout_seconds,
        )
        for _bug, variant in variants
    ]


def persist_variant_replay_results(
    session: Session,
    *,
    results: Iterable[ReplayJobResult],
    experiment_id: str,
    clean_run_id: str,
    clean_replay_id: str,
    cancellation_checker: Callable[[Session, str], None],
    error_cls: Type[Exception] = RuntimeError,
) -> None:
    for result in results:
        cancellation_checker(session, experiment_id)
        if not result.ok:
            raise error_cls(result.error or "variant replay job failed")
        output = result.result
        if not isinstance(output, VariantReplayJobOutput):
            raise error_cls("variant replay job returned an invalid result")
        metrics = dict(output.replay_metrics)
        metrics["clean_replay_id"] = clean_replay_id
        existing = session.scalar(
            select(ExperimentReplayRun).where(
                ExperimentReplayRun.experiment_clean_run_id == clean_run_id,
                ExperimentReplayRun.bug_variant_id == output.bug_variant_id,
            )
        )
        if existing is None:
            session.add(
                ExperimentReplayRun(
                    id=new_id(),
                    experiment_clean_run_id=clean_run_id,
                    bug_variant_id=output.bug_variant_id,
                    replay_id=output.replay_id,
                    captured_bug=output.captured_bug,
                    replay_metrics=metrics,
                )
            )
        else:
            existing.replay_id = output.replay_id
            existing.captured_bug = output.captured_bug
            existing.replay_metrics = metrics
        session.commit()
