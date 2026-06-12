# 编排器：串运行生命周期状态机（系统设计 §5）。
# 任何阶段失败：先落 run_event + trace_step，再改 status（§12.3）。Reflection 只一次由策略保证。
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.agents.llm import LLMClient
from app.agents.prompts import prompt_bundle
from app.agents.recorder import RunRecorder
from app.agents.report import build_report
from app.agents.runtime import AgentContext, PlanInput
from app.agents.strategies import get_strategy
from app.agents.strategies.base import Strategy
from app.core.errors import ErrorCode, TraceError
from app.schemas.records import TestReportRecord, TestRunRecord
from app.schemas.strategy import StrategyVersionSpec
from app.schemas.trace import RunEvent
from app.tools.base import ToolContext, ToolRegistry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunOutcome:
    run: TestRunRecord
    report: Optional[TestReportRecord]


def freeze_strategy_snapshot(strategy_spec: StrategyVersionSpec) -> dict:
    return {
        "workflow_type": strategy_spec.workflow_type,
        "model_provider": strategy_spec.model_provider,
        "model_name": strategy_spec.model_name,
        "model_params": strategy_spec.model_params,
        "tool_schema_ref": strategy_spec.tool_schema_ref,
        "allow_reflection": strategy_spec.allow_reflection,
        "max_tool_calls": strategy_spec.max_tool_calls,
        "prompts": prompt_bundle(strategy_spec),
    }


def freeze_runtime_snapshot() -> dict:
    return {"executor": "local_subprocess", "note": "V1 单机 subprocess，非安全沙箱"}


def execute_run(
    *,
    tools: ToolContext,
    registry: ToolRegistry,
    llm: LLMClient,
    recorder: RunRecorder,
    strategy_spec: StrategyVersionSpec,
    plan_input: PlanInput,
    run: Optional[TestRunRecord] = None,
    strategy_obj: Optional[Strategy] = None,
    artifacts_dir=None,
) -> RunOutcome:
    run = run or TestRunRecord(strategy_version_id=strategy_spec.id)
    # 冻结策略快照：完整 prompt bundle（system+contract+plan/generate/reflect 模板）+ 模型参数，
    # 不允许只存 ref——以后改 prompts.py，历史 run 仍可复现（V1实施清单 §3）
    run.strategy_snapshot = freeze_strategy_snapshot(strategy_spec)
    run.runtime_snapshot = freeze_runtime_snapshot()
    recorder.save_run(run)  # queued

    ctx = AgentContext(
        run=run,
        tools=tools,
        registry=registry,
        llm=llm,
        recorder=recorder,
        strategy=strategy_spec,
        max_tool_calls=strategy_spec.max_tool_calls,
    )
    report: Optional[TestReportRecord] = None
    run.started_at = _now()
    try:
        ctx.set_stage("preparing")
        strat = strategy_obj or get_strategy(strategy_spec.workflow_type)
        suspected = strat.run(ctx, plan_input)
        ctx.set_stage("summarizing")
        report = build_report(ctx, suspected_code_bug=suspected, artifacts_dir=artifacts_dir)
        recorder.save_report(report)
        _finish(ctx, "completed")
    except TraceError as e:
        _fail(ctx, e.code, e.message)
    except Exception as e:  # 兜底：任何未预期异常转成 failed + 错误码，绝不留悬空状态
        _fail(ctx, ErrorCode.RUNNER_INTERNAL_ERROR, f"{type(e).__name__}: {e}")
    return RunOutcome(run=run, report=report)


def _finish(ctx: AgentContext, status: str) -> None:
    before = ctx.run.status
    ctx.recorder.add_run_event(
        RunEvent(run_id=ctx.run_id, stage=None, event_type="run_finish",
                 status_before=before, status_after=status, message="运行完成")
    )
    ctx.run.status = status
    ctx.run.stage = None
    ctx.run.finished_at = _now()
    ctx.recorder.save_run(ctx.run)


def _fail(ctx: AgentContext, code: ErrorCode, message: str) -> None:
    before = ctx.run.status
    stage = ctx.run.stage  # 保留失败发生时的阶段
    code_str = code.value if hasattr(code, "value") else str(code)
    # §12.3：先 event + trace，再改 status
    ctx.recorder.add_run_event(
        RunEvent(run_id=ctx.run_id, stage=stage, event_type="run_failed",
                 status_before=before, status_after="failed", message=message)
    )
    ctx.trace("system", "运行失败", status="error", error=f"[{code_str}] {message}")
    ctx.run.status = "failed"
    ctx.run.error_code = code_str
    ctx.run.error_message = message
    ctx.run.finished_at = _now()
    ctx.recorder.save_run(ctx.run)
