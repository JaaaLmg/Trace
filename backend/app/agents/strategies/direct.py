# Direct：不规划、不反思。一个任务，analyze → generate → run，一把过。
from __future__ import annotations

from app.agents.runtime import AgentContext, PlanInput
from app.agents.strategies import common
from app.agents.strategies.base import Strategy
from app.schemas.records import RunPlanItemRecord


class DirectStrategy(Strategy):
    workflow_type = "direct"

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
        _, suspected = common.execute_item(
            ctx, analysis, plan_input, item, "tests/generated/test_generated.py", allow_reflection=False
        )
        return suspected
