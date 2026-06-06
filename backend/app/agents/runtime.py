# Agent 运行时：AgentContext 是三策略共享的执行环境。
# 它负责工具调用、LLM 结构化输出、trace 落库、tool-call 预算、status/stage 推进——
# 策略只管「编排哪几步」，落库和审计统一在这里，保证「每一步都落库」。
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Type

from pydantic import BaseModel

from app.agents.llm import LLMClient, Message
from app.agents.recorder import RunRecorder
from app.agents.structured import generate_structured
from app.core.errors import ErrorCode, TraceError
from app.schemas.records import TestRunRecord
from app.schemas.strategy import StrategyVersionSpec
from app.schemas.trace import RunEvent, Stage, StepType, TraceStep
from app.tools.base import ToolContext, ToolRegistry


def _summary(text, n: int = 300):
    if text is None:
        return None
    text = str(text)
    return text if len(text) <= n else text[:n] + "…"


def _outsum(out: BaseModel) -> str:
    name = out.__class__.__name__
    if hasattr(out, "passed") and hasattr(out, "failed"):
        return f"{name}: passed={out.passed} failed={out.failed} collected={getattr(out, 'collected', 0)}"
    return name


@dataclass
class PlanInput:
    """一次运行的目标与预算（来自 test_plan + budget_override）。"""

    target_scope: list[str]
    goal: str
    allow_reflection: bool = False
    timeout_seconds: int = 120


@dataclass
class AgentContext:
    run: TestRunRecord
    tools: ToolContext
    registry: ToolRegistry
    llm: LLMClient
    recorder: RunRecorder
    strategy: StrategyVersionSpec
    max_tool_calls: int = 12
    _step_index: int = 0
    current_attempt_id: Optional[str] = None

    @property
    def run_id(self) -> str:
        return self.run.id

    def _next_index(self) -> int:
        self._step_index += 1
        return self._step_index

    def set_stage(self, stage: Stage) -> None:
        before = self.run.status
        # §12.3：先落事件，再改状态
        self.recorder.add_run_event(
            RunEvent(
                run_id=self.run_id,
                stage=stage,
                event_type="stage_enter",
                status_before=before,
                status_after="running",
                message=f"进入 {stage}",
            )
        )
        self.run.status = "running"
        self.run.stage = stage
        self.recorder.save_run(self.run)

    def trace(
        self,
        step_type: StepType,
        name: str,
        *,
        tool_name=None,
        input_summary=None,
        output_summary=None,
        payload=None,
        tokens=None,
        duration_ms=None,
        status="ok",
        error=None,
    ) -> None:
        self.recorder.add_trace_step(
            TraceStep(
                run_id=self.run_id,
                attempt_id=self.current_attempt_id,
                step_index=self._next_index(),
                step_type=step_type,
                name=name,
                tool_name=tool_name,
                input_summary=_summary(input_summary),
                output_summary=_summary(output_summary),
                payload=payload,
                tokens=tokens,
                duration_ms=duration_ms,
                status=status,
                error=error,
            )
        )

    def call_tool(self, name: str, raw_input: dict) -> BaseModel:
        if self.run.tool_call_count >= self.max_tool_calls:
            raise TraceError(ErrorCode.TOOL_ARGUMENT_ERROR, f"超出工具调用预算 {self.max_tool_calls}")
        self.trace("tool_call", f"调用 {name}", tool_name=name, input_summary=repr(raw_input), payload={"input": raw_input})
        t0 = time.monotonic()
        try:
            out = self.registry.call(self.tools, name, raw_input)
        except TraceError as e:
            # 失败也要留痕：先把 observation 落库，再把异常抛给状态机
            self.trace("observation", f"{name} 失败", tool_name=name, status="error", error=e.message)
            raise
        dur = int((time.monotonic() - t0) * 1000)
        self.run.tool_call_count += 1
        self.recorder.save_run(self.run)
        self.trace(
            "observation",
            f"{name} 返回",
            tool_name=name,
            output_summary=_outsum(out),
            payload={"output": out.model_dump()},
            duration_ms=dur,
        )
        return out

    def think(self, messages: list[Message], schema: Type[BaseModel], *, step_type: StepType = "generation", name: str = "LLM 生成") -> BaseModel:
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        try:
            res = generate_structured(self.llm, messages, schema)
        except TraceError as e:
            # 失败也留痕：失败重试同样烧了 token，必须累计（否则失败 run 的成本指标撒谎），
            # 再把每次 LLM 调用（输入/原始输出/错误）落进 trace，然后抛
            details = e.details or {}
            logs = details.get("attempt_logs", [])
            tokens = details.get("tokens", 0)
            self.run.total_tokens += tokens
            self.recorder.save_run(self.run)
            self.trace(
                step_type,
                f"{name}（结构化输出失败）",
                input_summary=last_user,
                tokens=tokens,
                status="error",
                error=e.message,
                payload={"attempt_logs": logs, "attempts": len(logs)},
            )
            raise
        self.run.total_tokens += res.tokens
        self.recorder.save_run(self.run)
        # 把每次 LLM 调用的完整输入/原始输出/错误都落 trace：重试也能逐次复现
        self.trace(
            step_type,
            name,
            tokens=res.tokens,
            input_summary=last_user,
            output_summary=str(res.value),
            payload={"attempt_logs": res.attempt_logs, "attempts": res.attempts, "value": res.value.model_dump()},
        )
        return res.value
