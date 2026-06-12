from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.agents.recorder import RunRecorder
from app.core.ids import new_id
from app.models import (
    GeneratedTestCase,
    GeneratedTestFile,
    PytestCaseResult,
    RunArtifact,
    RunAttempt,
    RunEvent as RunEventModel,
    RunPlanItem,
    TestReport,
    TestRun,
    TraceStep as TraceStepModel,
)
from app.schemas.records import (
    GeneratedTestCaseRecord,
    GeneratedTestFileRecord,
    PytestCaseResultRecord,
    RunArtifactRecord,
    RunAttemptRecord,
    RunPlanItemRecord,
    TestReportRecord,
    TestRunRecord,
)
from app.schemas.trace import RunEvent, TraceStep


def _parse_dt(value: str | None):
    if not value:
        return None
    return datetime.fromisoformat(value)


class SQLAlchemyRunRecorder(RunRecorder):
    def __init__(self, session: Session, *, auto_commit: bool = True) -> None:
        self.session = session
        self.auto_commit = auto_commit

    def _flush(self) -> None:
        if self.auto_commit:
            self.session.commit()
        else:
            self.session.flush()

    def save_run(self, run: TestRunRecord) -> None:
        obj = self.session.get(TestRun, run.id)
        if obj is None:
            obj = TestRun(id=run.id)
            self.session.add(obj)
        obj.test_plan_id = run.test_plan_id
        obj.retry_of_run_id = run.retry_of_run_id
        obj.project_snapshot_id = run.project_snapshot_id
        obj.runtime_profile_id = run.runtime_profile_id
        obj.strategy_version_id = run.strategy_version_id
        obj.runtime_snapshot = run.runtime_snapshot
        obj.strategy_snapshot = run.strategy_snapshot
        obj.status = run.status
        obj.stage = run.stage
        obj.started_at = _parse_dt(run.started_at)
        obj.finished_at = _parse_dt(run.finished_at)
        obj.total_tokens = run.total_tokens
        obj.tool_call_count = run.tool_call_count
        obj.pytest_summary = run.pytest_summary
        obj.error_code = run.error_code
        obj.error_message = run.error_message
        self._flush()

    def add_run_event(self, event: RunEvent) -> None:
        self.session.add(
            RunEventModel(
                id=new_id(),
                run_id=event.run_id,
                stage=event.stage,
                event_type=event.event_type,
                status_before=event.status_before,
                status_after=event.status_after,
                message=event.message,
            )
        )
        self._flush()

    def add_trace_step(self, step: TraceStep) -> None:
        self.session.add(
            TraceStepModel(
                id=new_id(),
                run_id=step.run_id,
                attempt_id=step.attempt_id,
                step_index=step.step_index,
                step_type=step.step_type,
                name=step.name,
                input_summary=step.input_summary,
                output_summary=step.output_summary,
                tool_name=step.tool_name,
                payload=step.payload,
                tokens=step.tokens,
                duration_ms=step.duration_ms,
                status=step.status,
                error=step.error,
            )
        )
        self._flush()

    def add_plan_item(self, item: RunPlanItemRecord) -> None:
        self.session.add(
            RunPlanItem(
                id=item.id,
                run_id=item.run_id,
                index=item.index,
                target_type=item.target_type,
                target_ref=item.target_ref,
                goal=item.goal,
                planned_assertions=item.planned_assertions,
                status=item.status,
            )
        )
        self._flush()

    def save_plan_item(self, item: RunPlanItemRecord) -> None:
        obj = self.session.get(RunPlanItem, item.id)
        if obj is None:
            self.add_plan_item(item)
            return
        obj.run_id = item.run_id
        obj.index = item.index
        obj.target_type = item.target_type
        obj.target_ref = item.target_ref
        obj.goal = item.goal
        obj.planned_assertions = item.planned_assertions
        obj.status = item.status
        self._flush()

    def add_attempt(self, attempt: RunAttemptRecord) -> None:
        self.session.add(
            RunAttempt(
                id=attempt.id,
                run_plan_item_id=attempt.run_plan_item_id,
                attempt_no=attempt.attempt_no,
                kind=attempt.kind,
                status=attempt.status,
                pytest_exit_code=attempt.pytest_exit_code,
                error_code=attempt.error_code,
                reflection_reason=attempt.reflection_reason,
            )
        )
        self._flush()

    def save_attempt(self, attempt: RunAttemptRecord) -> None:
        obj = self.session.get(RunAttempt, attempt.id)
        if obj is None:
            self.add_attempt(attempt)
            return
        obj.run_plan_item_id = attempt.run_plan_item_id
        obj.attempt_no = attempt.attempt_no
        obj.kind = attempt.kind
        obj.status = attempt.status
        obj.pytest_exit_code = attempt.pytest_exit_code
        obj.error_code = attempt.error_code
        obj.reflection_reason = attempt.reflection_reason
        self._flush()

    def add_generated_file(self, f: GeneratedTestFileRecord) -> None:
        self.session.add(
            GeneratedTestFile(
                id=f.id,
                attempt_id=f.attempt_id,
                path=f.path,
                content_text=f.content_text,
                content_hash=f.content_hash,
                previous_file_id=f.previous_file_id,
                generation_reason=f.generation_reason,
            )
        )
        self._flush()

    def add_generated_cases(self, cases: list[GeneratedTestCaseRecord]) -> None:
        for case in cases:
            self.session.add(
                GeneratedTestCase(
                    id=case.id,
                    file_id=case.file_id,
                    nodeid=case.nodeid,
                    test_name=case.test_name,
                    start_line=case.start_line,
                    end_line=case.end_line,
                    target_route=case.target_route,
                    target_function=case.target_function,
                    assertion_summary=case.assertion_summary,
                    source_strategy_version_id=case.source_strategy_version_id,
                    adoption_status=case.adoption_status,
                    human_meaningfulness_score=case.human_meaningfulness_score,
                    rule_flags=case.rule_flags,
                )
            )
        self._flush()

    def add_pytest_results(self, results: list[PytestCaseResultRecord]) -> None:
        for result in results:
            self.session.add(
                PytestCaseResult(
                    id=result.id,
                    attempt_id=result.attempt_id,
                    generated_test_case_id=result.generated_test_case_id,
                    nodeid=result.nodeid,
                    mapping_status=result.mapping_status,
                    status=result.status,
                    duration_ms=result.duration_ms,
                    failure_type=result.failure_type,
                    failure_message=result.failure_message,
                    traceback_hash=result.traceback_hash,
                    is_collection_error=result.is_collection_error,
                )
            )
        self._flush()

    def add_artifact(self, artifact: RunArtifactRecord) -> None:
        self.session.add(
            RunArtifact(
                id=artifact.id,
                run_id=artifact.run_id,
                attempt_id=artifact.attempt_id,
                artifact_type=artifact.artifact_type,
                uri=artifact.uri,
                content_hash=artifact.content_hash,
                size_bytes=artifact.size_bytes,
                metadata_json=artifact.metadata,
            )
        )
        self._flush()

    def save_report(self, report: TestReportRecord) -> None:
        obj = self.session.get(TestReport, report.id)
        if obj is None:
            obj = TestReport(id=report.id, run_id=report.run_id)
            self.session.add(obj)
        obj.run_id = report.run_id
        obj.summary = report.summary
        obj.metrics = report.metrics
        obj.risk_notes = report.risk_notes
        obj.markdown_uri = report.markdown_uri
        obj.json_uri = report.json_uri
        self._flush()
