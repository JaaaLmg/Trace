# 种 3 条 strategy_versions（V1实施清单 §3）。不建 strategies 父表、不建 prompt/tool schema 版本表。
from __future__ import annotations

from app.schemas.strategy import StrategyVersionSpec

SEED_STRATEGIES: dict[str, StrategyVersionSpec] = {
    "direct": StrategyVersionSpec(
        id="sv-direct-v1",
        name="Direct v1",
        workflow_type="direct",
        allow_reflection=False,
        max_tool_calls=8,
        prompt_ref="direct_v1",
        tool_schema_ref="tools_v1",
    ),
    "plan_execute": StrategyVersionSpec(
        id="sv-plan-v1",
        name="Plan-and-Execute v1",
        workflow_type="plan_execute",
        allow_reflection=False,
        max_tool_calls=20,
        prompt_ref="plan_v1",
        tool_schema_ref="tools_v1",
    ),
    "react_reflection": StrategyVersionSpec(
        id="sv-react-v1",
        name="ReAct+Reflection v1",
        workflow_type="react_reflection",
        allow_reflection=True,
        max_tool_calls=12,
        prompt_ref="react_v1",
        tool_schema_ref="tools_v1",
    ),
}


def seed_list() -> list[StrategyVersionSpec]:
    return list(SEED_STRATEGIES.values())
