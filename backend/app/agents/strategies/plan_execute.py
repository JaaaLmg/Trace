# Plan-and-Execute：先让 LLM 把目标拆成多个任务，每个任务各生成各执行。不反思。
from __future__ import annotations

from app.agents import prompts
from app.agents.runtime import AgentContext, PlanInput
from app.agents.strategies import common
from app.agents.strategies.base import Strategy
from app.schemas.agent import PlanItemDraft, PlanOutput
from app.schemas.records import RunPlanItemRecord


class PlanExecuteStrategy(Strategy):
    workflow_type = "plan_execute"

    def run(self, ctx: AgentContext, plan_input: PlanInput) -> bool:
        analysis = common.do_analyze(ctx, plan_input.target_scope)
        ctx.set_stage("planning")
        plan: PlanOutput = ctx.think(
            prompts.build_plan_messages(ctx.strategy, analysis, plan_input.target_scope, plan_input.goal),
            PlanOutput,
            step_type="plan",
            name="拆分测试任务",
        )
        drafts = plan.items or [
            PlanItemDraft(index=0, target_type="goal", target_ref="all", goal=plan_input.goal)
        ]

        suspected_any = False
        for d in drafts:
            item = RunPlanItemRecord(
                run_id=ctx.run_id,
                index=d.index,
                target_type=d.target_type,
                target_ref=d.target_ref,
                goal=d.goal,
                planned_assertions=d.planned_assertions,
                status="generating",
            )
            ctx.recorder.add_plan_item(item)
            _, suspected = common.execute_item(
                ctx, analysis, plan_input, item, f"tests/generated/test_item{d.index}.py", allow_reflection=False
            )
            suspected_any = suspected_any or suspected
        return suspected_any
