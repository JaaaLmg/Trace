from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
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


def _clip(value: str | None, limit: int) -> str | None:
    if value is None or len(value) <= limit:
        return value
    return value[: max(0, limit - 14)] + "...<truncated>"


class SQLAlchemyRunRecorder(RunRecorder):
    def __init__(self, session: Session, *, auto_commit: bool = True) -> None:
        # recorder 是 A/B 之间最关键的适配层：
        # A 线只知道“写记录”，B 线负责把这些记录准确落到 SQLAlchemy/数据库。
        self.session = session
        self.auto_commit = auto_commit

    def _flush(self) -> None:
        # 默认每次写完立即 commit，优先确保调试期数据可见。
        # 后续若想把事务边界上提，可传 auto_commit=False。
        if self.auto_commit:
            self.session.commit()
        else:
            self.session.flush()

    def save_run(self, run: TestRunRecord) -> None:
        # run 主记录是 upsert：A 线会在不同阶段反复更新 status/stage/summary。
        if run.test_plan_id is None:
            raise ValueError("test_plan_id is required when persisting a run")
        obj = self.session.get(TestRun, run.id)
        if obj is None:
            obj = TestRun(id=run.id)
            self.session.add(obj)
            preserve_cancelled = False
        else:
            self.session.refresh(obj)
            preserve_cancelled = obj.status == "cancelled" and run.status != "cancelled"
        obj.test_plan_id = run.test_plan_id
        obj.retry_of_run_id = run.retry_of_run_id
        obj.project_snapshot_id = run.project_snapshot_id
        obj.runtime_profile_id = run.runtime_profile_id
        obj.strategy_version_id = run.strategy_version_id
        obj.runtime_snapshot = run.runtime_snapshot
        obj.strategy_snapshot = run.strategy_snapshot
        if not preserve_cancelled:
            obj.status = run.status
            obj.stage = run.stage
            obj.finished_at = _parse_dt(run.finished_at)
        obj.started_at = _parse_dt(run.started_at)
        obj.total_tokens = run.total_tokens
        obj.tool_call_count = run.tool_call_count
        obj.pytest_summary = run.pytest_summary
        obj.error_code = run.error_code
        obj.error_message = run.error_message
        self._flush()

    def add_run_event(self, event: RunEvent) -> None:
        # 事件流只追加不回写，保留完整状态机审计轨迹。
        self.session.add(
            RunEventModel(
                id=new_id(),
                run_id=event.run_id,
                stage=_clip(event.stage, 32),
                event_type=_clip(event.event_type, 64),
                status_before=_clip(event.status_before, 32),
                status_after=_clip(event.status_after, 32),
                message=event.message,
            )
        )
        self._flush()

    def add_trace_step(self, step: TraceStep) -> None:
        # trace step 对应前端时间线中的一个节点。
        self.session.add(
            TraceStepModel(
                id=new_id(),
                run_id=step.run_id,
                attempt_id=step.attempt_id,
                step_index=step.step_index,
                step_type=_clip(step.step_type, 32),
                name=_clip(step.name, 255) or "",
                input_summary=step.input_summary,
                output_summary=step.output_summary,
                tool_name=_clip(step.tool_name, 128),
                payload=step.payload,
                tokens=step.tokens,
                duration_ms=step.duration_ms,
                status=_clip(step.status, 16) or "ok",
                error=_clip(step.error, 255),
            )
        )
        self._flush()

    def add_plan_item(self, item: RunPlanItemRecord) -> None:
        # 计划项在 planning 阶段追加创建。
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
        # 计划项状态会随着执行推进改变，因此这里需要支持更新。
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
        # 每轮 initial/reflection 尝试先插入一条 attempt 记录。
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
        # attempt 会在执行后更新状态、pytest_exit_code、error_code 等。
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
        # 保存每轮生成出来的测试文件版本。
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
        # 从文件中解析出的逻辑用例单元，后续要和 pytest 结果做映射。
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
        # 保存 pytest 的单用例运行结果。
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
        # 保存文件型产物的元数据，不直接承载大文件内容。
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
        # 每个 run 最终只保留一份汇总报告，因此这里仍是 upsert 语义。
        obj = self.session.get(TestReport, report.id)
        if obj is None:
            stmt = select(TestReport).where(TestReport.run_id == report.run_id)
            obj = self.session.scalars(stmt).one_or_none()
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

    def list_plan_items(self, run_id: str) -> list[RunPlanItem]:
        stmt = select(RunPlanItem).where(RunPlanItem.run_id == run_id).order_by(RunPlanItem.index.asc())
        return list(self.session.scalars(stmt))

    def list_attempts(self, run_id: str) -> list[RunAttempt]:
        stmt = (
            select(RunAttempt)
            .join_from(RunAttempt, RunPlanItem)
            .where(RunPlanItem.run_id == run_id)
            .order_by(RunAttempt.attempt_no.asc())
        )
        return list(self.session.scalars(stmt))

    def list_pytest_results(self, run_id: str) -> list[PytestCaseResult]:
        stmt = (
            select(PytestCaseResult)
            .join_from(PytestCaseResult, RunAttempt)
            .join_from(RunAttempt, RunPlanItem)
            .where(RunPlanItem.run_id == run_id)
            .order_by(PytestCaseResult.nodeid.asc())
        )
        return list(self.session.scalars(stmt))

    def list_generated_files(self, run_id: str) -> list[GeneratedTestFile]:
        stmt = (
            select(GeneratedTestFile)
            .join_from(GeneratedTestFile, RunAttempt)
            .join_from(RunAttempt, RunPlanItem)
            .where(RunPlanItem.run_id == run_id)
            .order_by(GeneratedTestFile.created_at.asc())
        )
        return list(self.session.scalars(stmt))

    def list_generated_cases(self, run_id: str) -> list[GeneratedTestCase]:
        stmt = (
            select(GeneratedTestCase)
            .join_from(GeneratedTestCase, GeneratedTestFile)
            .join_from(GeneratedTestFile, RunAttempt)
            .join_from(RunAttempt, RunPlanItem)
            .where(RunPlanItem.run_id == run_id)
            .order_by(GeneratedTestCase.test_name.asc())
        )
        return list(self.session.scalars(stmt))
