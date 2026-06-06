# trace 事件 schema（A + B 共定）。对齐 系统设计.md §5 / §9.2
# 这是 Agent 过程审计的灵魂，每一步都要落库
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# 外部状态
RunStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
# 内部阶段：只在 status=running 时有意义
Stage = Literal[
    "preparing",
    "analyzing",
    "planning",
    "generating",
    "executing",
    "reflecting",
    "reexecuting",
    "summarizing",
]
StepType = Literal[
    "plan", "tool_call", "observation", "generation", "reflection", "report", "system"
]
StepStatus = Literal["ok", "error"]


class TraceStep(BaseModel):
    run_id: str
    attempt_id: Optional[str] = None
    step_index: int
    step_type: StepType
    name: str
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    tool_name: Optional[str] = None
    # payload 存完整输入输出（结构化），前端 trace 详情用
    payload: Optional[dict[str, Any]] = None
    tokens: Optional[int] = None
    duration_ms: Optional[int] = None
    status: StepStatus = "ok"
    error: Optional[str] = None


class RunEvent(BaseModel):
    run_id: str
    stage: Optional[Stage] = None
    event_type: str
    status_before: Optional[RunStatus] = None
    status_after: Optional[RunStatus] = None
    message: Optional[str] = None
