from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.artifacts import PytestCaseResult, RunArtifact, TestReport
from app.models.test_run import RunAttempt, RunPlanItem, TestRun
from app.models.trace import RunEvent, TraceStep


def add_test_run(session: Session, run: TestRun) -> TestRun:
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def get_test_run(session: Session, run_id: str) -> TestRun | None:
    return session.get(TestRun, run_id)


def list_trace_steps(session: Session, run_id: str) -> list[TraceStep]:
    stmt = select(TraceStep).where(TraceStep.run_id == run_id).order_by(TraceStep.step_index.asc())
    return list(session.scalars(stmt))


def list_run_events(session: Session, run_id: str) -> list[RunEvent]:
    stmt = select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.created_at.asc())
    return list(session.scalars(stmt))


def list_run_attempts(session: Session, run_id: str) -> list[RunAttempt]:
    stmt = (
        select(RunAttempt)
        .join_from(RunAttempt, RunPlanItem)
        .join_from(RunPlanItem, TestRun)
        .where(TestRun.id == run_id)
        .order_by(RunAttempt.attempt_no.asc())
    )
    return list(session.scalars(stmt))


def list_pytest_results(session: Session, run_id: str) -> list[PytestCaseResult]:
    stmt = (
        select(PytestCaseResult)
        .join_from(PytestCaseResult, RunAttempt)
        .join_from(RunAttempt, RunPlanItem)
        .join_from(RunPlanItem, TestRun)
        .where(TestRun.id == run_id)
        .order_by(PytestCaseResult.nodeid.asc())
    )
    return list(session.scalars(stmt))


def list_run_artifacts(session: Session, run_id: str) -> list[RunArtifact]:
    stmt = select(RunArtifact).where(RunArtifact.run_id == run_id).order_by(RunArtifact.created_at.asc())
    return list(session.scalars(stmt))


def get_report(session: Session, run_id: str) -> TestReport | None:
    stmt = select(TestReport).where(TestReport.run_id == run_id)
    return session.scalars(stmt).first()


def list_run_plan_items(session: Session, run_id: str) -> list[RunPlanItem]:
    stmt = select(RunPlanItem).where(RunPlanItem.run_id == run_id).order_by(RunPlanItem.index.asc())
    return list(session.scalars(stmt))
