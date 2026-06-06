# 持久化端口 + 内存实现。A 与 B 的边界：A 产出过程数据经此落库，B 接 SQLAlchemy 实现同一协议。
from __future__ import annotations

from typing import Protocol

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


class RunRecorder(Protocol):
    """过程数据落库端口。系统设计 §12.3 的写入顺序由调用方（runtime/orchestrator）保证。"""

    def save_run(self, run: TestRunRecord) -> None: ...  # upsert
    def add_run_event(self, event: RunEvent) -> None: ...
    def add_trace_step(self, step: TraceStep) -> None: ...
    def add_plan_item(self, item: RunPlanItemRecord) -> None: ...
    def save_plan_item(self, item: RunPlanItemRecord) -> None: ...  # 更新状态用
    def add_attempt(self, attempt: RunAttemptRecord) -> None: ...
    def save_attempt(self, attempt: RunAttemptRecord) -> None: ...  # 更新状态用
    def add_generated_file(self, f: GeneratedTestFileRecord) -> None: ...
    def add_generated_cases(self, cases: list[GeneratedTestCaseRecord]) -> None: ...
    def add_pytest_results(self, results: list[PytestCaseResultRecord]) -> None: ...
    def add_artifact(self, artifact: RunArtifactRecord) -> None: ...
    def save_report(self, report: TestReportRecord) -> None: ...


class InMemoryRecorder:
    """V1 默认实现：全存内存。报告生成和测试断言直接读这些列表/字典。"""

    def __init__(self) -> None:
        self.runs: dict[str, TestRunRecord] = {}
        self.run_events: list[RunEvent] = []
        self.trace_steps: list[TraceStep] = []
        self.plan_items: list[RunPlanItemRecord] = []
        self.attempts: dict[str, RunAttemptRecord] = {}
        self.files: list[GeneratedTestFileRecord] = []
        self.cases: list[GeneratedTestCaseRecord] = []
        self.pytest_results: list[PytestCaseResultRecord] = []
        self.artifacts: list[RunArtifactRecord] = []
        self.reports: list[TestReportRecord] = []

    def save_run(self, run: TestRunRecord) -> None:
        self.runs[run.id] = run

    def add_run_event(self, event: RunEvent) -> None:
        self.run_events.append(event)

    def add_trace_step(self, step: TraceStep) -> None:
        self.trace_steps.append(step)

    def add_plan_item(self, item: RunPlanItemRecord) -> None:
        self.plan_items.append(item)

    def save_plan_item(self, item: RunPlanItemRecord) -> None:
        for i, x in enumerate(self.plan_items):
            if x.id == item.id:
                self.plan_items[i] = item
                return
        self.plan_items.append(item)

    def add_attempt(self, attempt: RunAttemptRecord) -> None:
        self.attempts[attempt.id] = attempt

    def save_attempt(self, attempt: RunAttemptRecord) -> None:
        self.attempts[attempt.id] = attempt

    def add_generated_file(self, f: GeneratedTestFileRecord) -> None:
        self.files.append(f)

    def add_generated_cases(self, cases: list[GeneratedTestCaseRecord]) -> None:
        self.cases.extend(cases)

    def add_pytest_results(self, results: list[PytestCaseResultRecord]) -> None:
        self.pytest_results.extend(results)

    def add_artifact(self, artifact: RunArtifactRecord) -> None:
        self.artifacts.append(artifact)

    def save_report(self, report: TestReportRecord) -> None:
        self.reports.append(report)

    # ---- 查询便捷方法（报告/测试用）----
    def steps_of(self, run_id: str) -> list[TraceStep]:
        return [s for s in self.trace_steps if s.run_id == run_id]

    def results_of_attempt(self, attempt_id: str) -> list[PytestCaseResultRecord]:
        return [r for r in self.pytest_results if r.attempt_id == attempt_id]
