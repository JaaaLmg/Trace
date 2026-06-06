# 策略注册表。get_strategy 内懒加载具体策略，避免 import 期循环。
from __future__ import annotations

from app.agents.strategies.base import Strategy
from app.core.errors import ErrorCode, TraceError


def get_strategy(workflow_type: str) -> Strategy:
    from app.agents.strategies.direct import DirectStrategy
    from app.agents.strategies.plan_execute import PlanExecuteStrategy
    from app.agents.strategies.react_reflection import ReactReflectionStrategy

    registry = {
        s.workflow_type: s
        for s in (DirectStrategy(), PlanExecuteStrategy(), ReactReflectionStrategy())
    }
    if workflow_type not in registry:
        raise TraceError(ErrorCode.TOOL_ARGUMENT_ERROR, f"未知 workflow_type: {workflow_type}")
    return registry[workflow_type]
