from __future__ import annotations

from pathlib import Path

from app.agents.llm import MockLLM
from app.agents.orchestrator import execute_run
from app.agents.runtime import PlanInput
from app.core.ids import new_id
from app.models.trace import RunEvent
from app.models.project import ProjectSnapshot
from app.models.strategy import StrategyVersion
from app.models.test_run import TestRun
from app.recorders.sqlalchemy_recorder import SQLAlchemyRunRecorder
from app.repositories.projects import get_project
from app.repositories.strategies import get_strategy_version
from app.repositories.test_plans import get_test_plan
from app.repositories.test_runs import get_test_run
from app.schemas.records import TestRunRecord
from app.schemas.strategy import StrategyVersionSpec
from app.tools import default_registry
from app.tools.base import ToolContext
from sqlalchemy.orm import Session


def _default_mock_responder(messages):
    blob = "\n".join(m.content for m in messages)
    if "TASK: PLAN" in blob:
        return '{"items":[{"index":0,"target_type":"goal","target_ref":"all","goal":"覆盖目标","planned_assertions":["核心断言"]}]}'
    if "TASK: REFLECT" in blob:
        return '{"fixed_content":"from calc import add\\n\\ndef test_add():\\n    assert add(2, 3) == 5\\n","fix_reason":"修正断言","changed_points":["6 -> 5"],"lowered_assertion_strength":false,"suspected_code_bug":false}'
    return '{"test_file_content":"from calc import add\\n\\ndef test_add():\\n    assert add(2, 3) == 5\\n","cases":[{"test_name":"test_add","target_function":"add","assertion_summary":"2+3=5"}],"coverage_notes":"sync mock run"}'


def _mock_llm():
    return MockLLM(_default_mock_responder)


def _strategy_spec_from_model(model: StrategyVersion) -> StrategyVersionSpec:
    return StrategyVersionSpec(
        id=model.id,
        name=model.name,
        workflow_type=model.workflow_type,
        model_provider=model.model_provider,
        model_name=model.model_name,
        model_params=model.model_params,
        allow_reflection=model.allow_reflection,
        max_tool_calls=model.max_tool_calls,
        prompt_ref=model.prompt_ref,
        tool_schema_ref=model.tool_schema_ref,
    )


def _artifacts_dir(snapshot_root: Path, run_id: str) -> Path:
    return snapshot_root / ".trace_artifacts" / run_id


def _run_record_from_model(run: TestRun) -> TestRunRecord:
    return TestRunRecord(
        id=run.id,
        test_plan_id=run.test_plan_id,
        retry_of_run_id=run.retry_of_run_id,
        project_snapshot_id=run.project_snapshot_id,
        runtime_profile_id=run.runtime_profile_id,
        strategy_version_id=run.strategy_version_id,
        runtime_snapshot=run.runtime_snapshot or {},
        strategy_snapshot=run.strategy_snapshot or {},
        status=run.status,
        stage=run.stage,
        started_at=run.started_at.isoformat() if run.started_at else None,
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        total_tokens=run.total_tokens,
        tool_call_count=run.tool_call_count,
        pytest_summary=run.pytest_summary or {},
        error_code=run.error_code,
        error_message=run.error_message,
    )


def create_run(
    session: Session,
    *,
    plan_id: str,
    snapshot_id: str,
    strategy_version_id: str | None = None,
    budget_override: dict | None = None,
    output_options: dict | None = None,
) -> TestRun:
    plan = get_test_plan(session, plan_id)
    if plan is None:
        raise ValueError("test plan not found")
    snapshot = session.get(ProjectSnapshot, snapshot_id)
    if snapshot is None:
        raise ValueError("snapshot not found")
    strategy_id = strategy_version_id or plan.default_strategy_version_id
    if not strategy_id:
        raise ValueError("strategy_version_id is required when test plan has no default strategy")
    strategy = get_strategy_version(session, strategy_id)
    if strategy is None:
        raise ValueError("strategy not found")

    run = TestRun(
        id=new_id(),
        test_plan_id=plan.id,
        project_snapshot_id=snapshot.id,
        strategy_version_id=strategy.id,
        runtime_snapshot={"mode": "local_sync_v1"},
        strategy_snapshot={},
        status="queued",
        pytest_summary={},
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def enqueue_run(
    session: Session,
    *,
    run_id: str,
    budget_override: dict | None = None,
) -> TestRun:
    from app.workers.tasks import execute_run_task

    run = get_test_run(session, run_id)
    if run is None:
        raise ValueError("run not found")
    session.add(
        RunEvent(
            id=new_id(),
            run_id=run.id,
            stage=None,
            event_type="run_enqueued",
            status_before=run.status,
            status_after="queued",
            message="运行已加入 Celery 队列",
        )
    )
    session.commit()
    execute_run_task.delay(run.id, budget_override or {})
    session.refresh(run)
    return run


def execute_run_sync(
    session: Session,
    *,
    run_id: str,
    budget_override: dict | None = None,
) -> TestRun:
    run = get_test_run(session, run_id)
    if run is None:
        raise ValueError("run not found")
    plan = get_test_plan(session, run.test_plan_id) if run.test_plan_id else None
    if plan is None:
        raise ValueError("test plan not found")
    snapshot = session.get(ProjectSnapshot, run.project_snapshot_id)
    if snapshot is None:
        raise ValueError("snapshot not found")
    strategy = get_strategy_version(session, run.strategy_version_id)
    if strategy is None:
        raise ValueError("strategy not found")
    project = get_project(session, snapshot.project_id)
    if project is None:
        raise ValueError("project not found")

    root = Path(snapshot.root_path)
    test_write_dir = root / "tests" / "generated"
    test_write_dir.mkdir(parents=True, exist_ok=True)
    recorder = SQLAlchemyRunRecorder(session)
    strategy_spec = _strategy_spec_from_model(strategy)
    budget = dict(plan.budget or {})
    if budget_override:
        budget.update(budget_override)
    llm = _mock_llm()

    execute_run(
        tools=ToolContext(root=root, test_write_dir=test_write_dir),
        registry=default_registry(),
        llm=llm,
        recorder=recorder,
        strategy_spec=strategy_spec,
        plan_input=PlanInput(
            target_scope=list(plan.target_scope or []),
            goal=plan.goal,
            allow_reflection=bool(budget.get("allow_reflection", False)),
            timeout_seconds=int(budget.get("timeout_seconds", 120)),
        ),
        run=_run_record_from_model(run),
        artifacts_dir=_artifacts_dir(root, run.id),
    )

    refreshed = get_test_run(session, run.id)
    assert refreshed is not None
    return refreshed


def retry_run(session: Session, *, run_id: str) -> TestRun:
    original = get_test_run(session, run_id)
    if original is None:
        raise ValueError("run not found")
    clone = TestRun(
        id=new_id(),
        test_plan_id=original.test_plan_id,
        retry_of_run_id=original.id,
        project_snapshot_id=original.project_snapshot_id,
        strategy_version_id=original.strategy_version_id,
        runtime_snapshot=original.runtime_snapshot,
        strategy_snapshot=original.strategy_snapshot,
        status="queued",
        pytest_summary={},
    )
    session.add(clone)
    session.commit()
    session.refresh(clone)
    return clone


def retry_run_async(session: Session, *, run_id: str) -> TestRun:
    clone = retry_run(session, run_id=run_id)
    return enqueue_run(session, run_id=clone.id, budget_override=None)


def cancel_run(session: Session, *, run_id: str) -> TestRun:
    run = get_test_run(session, run_id)
    if run is None:
        raise ValueError("run not found")
    if run.status in {"completed", "failed", "cancelled"}:
        return run
    run.status = "cancelled"
    session.commit()
    session.refresh(run)
    return run
