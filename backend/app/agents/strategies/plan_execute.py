# Plan-and-Execute：先让 LLM 把目标拆成多个任务，每个任务各生成各执行。不反思。
from __future__ import annotations

from app.agents import prompts
from app.agents.runtime import AgentContext, PlanInput
from app.agents.strategies import common
from app.agents.strategies.base import Strategy
from app.schemas.agent import PlanItemDraft, PlanOutput
from app.schemas.records import RunPlanItemRecord
from app.schemas.tools import AnalyzeProjectOutput


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
        drafts = _normalize_plan_items(
            plan.items or [PlanItemDraft(index=0, target_type="goal", target_ref="all", goal=plan_input.goal)],
            analysis,
        )

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


def _normalize_plan_items(items: list[PlanItemDraft], analysis: AnalyzeProjectOutput) -> list[PlanItemDraft]:
    normalized: list[PlanItemDraft] = []
    for item in items:
        target_ref = _canonical_target_ref(item, analysis)
        if target_ref == item.target_ref:
            normalized.append(item)
        else:
            normalized.append(item.model_copy(update={"target_ref": target_ref}))
    return normalized


def _canonical_target_ref(item: PlanItemDraft, analysis: AnalyzeProjectOutput) -> str:
    ref = item.target_ref.strip()
    if item.target_type == "function":
        return _canonical_function_ref(ref, analysis) or ref
    if item.target_type == "route":
        return _canonical_route_ref(ref, analysis) or ref
    return ref


def _canonical_function_ref(ref: str, analysis: AnalyzeProjectOutput) -> str | None:
    wanted = ref.rsplit(".", 1)[-1]
    for fn in analysis.functions:
        if wanted == fn.name or wanted == _signature_name(fn.signature):
            return fn.name
    return None


def _canonical_route_ref(ref: str, analysis: AnalyzeProjectOutput) -> str | None:
    method, path = _split_route_ref(ref)
    lowered = ref.lower()
    for route in analysis.routes:
        canonical = f"{route.method.upper()} {route.path}"
        aliases = {
            canonical.lower(),
            route.path.lower(),
            route.handler.lower(),
            f"{route.method.upper()} {route.handler}".lower(),
        }
        if method and path:
            if method == route.method.upper() and path == route.path:
                return canonical
        if lowered in aliases:
            return canonical
    return None


def _split_route_ref(ref: str) -> tuple[str | None, str | None]:
    parts = ref.strip().split(maxsplit=1)
    if len(parts) == 2 and parts[0].upper() in {"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"}:
        return parts[0].upper(), parts[1].strip()
    return None, None


def _signature_name(signature: str) -> str:
    return signature.split("(", 1)[0].strip()
