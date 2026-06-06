# ReAct + Reflection：单任务生成→执行，失败且预算允许时反思一次（修测试 / 标疑似缺陷）。
from __future__ import annotations

from app.agents.runtime import AgentContext, PlanInput
from app.agents.strategies import common
from app.agents.strategies.base import Strategy
from app.schemas.records import RunPlanItemRecord


class ReactReflectionStrategy(Strategy):
    workflow_type = "react_reflection"

    def run(self, ctx: AgentContext, plan_input: PlanInput) -> bool:
        analysis = common.do_analyze(ctx, plan_input.target_scope)
        ctx.set_stage("planning")
        item = RunPlanItemRecord(
            run_id=ctx.run_id,
            index=0,
            target_type="goal",
            target_ref=",".join(plan_input.target_scope) or "all",
            goal=plan_input.goal,
            status="generating",
        )
        ctx.recorder.add_plan_item(item)
        # 反思能力 = 策略本身允许 且 本次预算允许（budget_override.allow_reflection）
        allow = ctx.strategy.allow_reflection and plan_input.allow_reflection
        _, suspected = common.execute_item(
            ctx, analysis, plan_input, item, "tests/generated/test_generated.py", allow_reflection=allow
        )
        return suspected
