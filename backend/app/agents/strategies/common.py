# 三策略共享的执行步骤。差异只在「编排」：Direct 单任务不反思、Plan-and-Execute 先拆多任务、
# ReAct+Reflection 单任务带一次反思。落库/映射/契约校验都收在这里，策略文件保持很薄。
from __future__ import annotations

import hashlib
from typing import Optional

from app.agents import prompts
from app.agents.case_mapping import base_nodeid, nodeid_for_case, parse_generated_cases, test_name_of
from app.agents.contract_guard import check_generation_contract, check_reflection_contract
from app.agents.runtime import AgentContext, PlanInput
from app.services.source_context import build_source_context_bundle
from app.core.errors import ErrorCode
from app.core.errors import TraceError
from app.schemas.agent import GenerationOutput, PlanItemDraft, ReflectionOutput
from app.schemas.records import (
    GeneratedTestCaseRecord,
    GeneratedTestFileRecord,
    PytestCaseResultRecord,
    RunAttemptRecord,
    RunPlanItemRecord,
)
from app.schemas.tools import AnalyzeProjectOutput, RunPytestOutput


def do_analyze(ctx: AgentContext, scope: list[str]) -> AnalyzeProjectOutput:
    ctx.set_stage("analyzing")
    analysis = ctx.call_tool("analyze_project", {"target_scope": scope})  # type: ignore[return-value]
    source_bundle = build_source_context_bundle(ctx.tools, scope, analysis)
    ctx.source_context_text = source_bundle.source_context_text
    ctx.context_completeness = source_bundle.context_completeness
    ctx.trace(
        "observation",
        "读取目标源码片段",
        output_summary=source_bundle.context_completeness.status,
        payload=source_bundle.context_completeness.model_dump(),
        status="ok",
    )
    return analysis


def make_attempt(ctx: AgentContext, plan_item_id: str, attempt_no: int, kind: str) -> RunAttemptRecord:
    a = RunAttemptRecord(run_plan_item_id=plan_item_id, attempt_no=attempt_no, kind=kind)
    ctx.recorder.add_attempt(a)
    ctx.current_attempt_id = a.id
    return a


def do_generate(ctx, attempt, analysis, scope, goal, item, target_path, *, previous_file_id=None):
    draft = _as_draft(item) if item is not None else None
    msgs = prompts.build_generate_messages(
        ctx.strategy,
        analysis,
        scope,
        goal,
        draft,
        source_context=ctx.source_context_text,
    )
    gen: GenerationOutput = ctx.think(msgs, GenerationOutput, step_type="generation", name="生成测试")
    violations = check_generation_contract(
        gen.test_file_content,
        gen.cases,
        target_type=getattr(draft, "target_type", None),
        target_ref=getattr(draft, "target_ref", None),
        allowed_request_fields=_model_field_names(analysis),
    )
    if violations:
        reason = "；".join(violations)
        attempt.status = "error"
        attempt.error_code = ErrorCode.PIPELINE_REJECT.value
        ctx.recorder.save_attempt(attempt)
        ctx.trace("generation", "生成测试契约拒绝：" + reason, status="error", error=reason)
        raise TraceError(ErrorCode.PIPELINE_REJECT, reason, details={"violations": violations})
    # 不信任 LLM 给的路径，强制写到策略指定的受控 target_path（白名单在 write_test_file 内）
    wout = ctx.call_tool(
        "write_test_file",
        {"attempt_id": attempt.id, "path": target_path, "content": gen.test_file_content, "reason": gen.coverage_notes or goal},
    )
    frec = GeneratedTestFileRecord(
        attempt_id=attempt.id,
        path=wout.path,
        content_text=gen.test_file_content,
        content_hash=wout.content_hash,
        previous_file_id=previous_file_id,
        generation_reason=gen.coverage_notes,
    )
    ctx.recorder.add_generated_file(frec)
    cases = _register_cases(ctx, frec, {c.test_name: c for c in gen.cases})
    return frec, cases


def do_run(ctx, attempt, test_paths, attempt_cases, timeout) -> RunPytestOutput:
    out: RunPytestOutput = ctx.call_tool(
        "run_pytest", {"attempt_id": attempt.id, "test_paths": test_paths, "timeout_seconds": timeout}
    )  # type: ignore[assignment]
    attempt.pytest_exit_code = out.exit_code
    _map_results(ctx, attempt, out, attempt_cases)
    attempt.status = "error" if out.error else ("passed" if _run_ok(out) else "failed")
    ctx.recorder.save_attempt(attempt)
    return out


def execute_item(ctx, analysis, plan_input: PlanInput, item, target_path, allow_reflection):
    """单任务闭环：initial(generate→run)，必要时 reflection 一次(rewrite→rerun)。
    返回 (最终 pytest 结果, 是否判定疑似业务缺陷)。"""
    a1 = make_attempt(ctx, item.id, 1, "initial")
    ctx.set_stage("generating")
    frec, cases = do_generate(ctx, a1, analysis, plan_input.target_scope, item.goal, item, target_path)
    ctx.set_stage("executing")
    out = do_run(ctx, a1, [frec.path], cases, plan_input.timeout_seconds)

    suspected = False
    if allow_reflection and _should_reflect(out):
        out2, suspected = _reflect_once(ctx, analysis, plan_input, item, frec, cases, out, target_path)
        if out2 is not None:
            out = out2

    item.status = "done" if _run_ok(out) else "failed"
    ctx.recorder.save_plan_item(item)
    return out, suspected


def _reflect_once(ctx, analysis, plan_input, item, prev_file, prev_cases, out, target_path):
    ctx.set_stage("reflecting")
    a2 = make_attempt(ctx, item.id, 2, "reflection")
    msgs = prompts.build_reflect_messages(
        ctx.strategy,
        analysis,
        prev_file.content_text or "",
        out,
        relevant_source=ctx.source_context_text,
    )
    refl: ReflectionOutput = ctx.think(msgs, ReflectionOutput, step_type="reflection", name="反思修复")
    a2.reflection_reason = refl.fix_reason

    # 模型自报疑似业务缺陷：不重写、保留失败（保留那份失败是安全方向，写进报告）
    if refl.suspected_code_bug:
        a2.status = "failed"
        ctx.recorder.save_attempt(a2)
        ctx.trace("reflection", "判定疑似业务缺陷，保留失败", output_summary=refl.fix_reason)
        return None, True

    # 契约闸门：静态比对首轮/修复版，别只信模型自报的 lowered_assertion_strength
    #（别让被审的人自己打分）。任一信号判定削弱（含模型自认）= 违规，不采纳，保留首轮失败。
    violations = check_reflection_contract(prev_file.content_text or "", refl.fixed_content)
    if refl.lowered_assertion_strength:
        violations = violations + ["模型自报削弱了断言"]
    if violations:
        reason = "；".join(violations)
        a2.status = "error"
        a2.error_code = ErrorCode.REFLECTION_CONTRACT_VIOLATION.value
        ctx.recorder.save_attempt(a2)
        ctx.trace("reflection", "Reflection 契约违规：" + reason, status="error", error=reason)
        return None, False

    # 正常修复：rewrite → rerun
    wout = ctx.call_tool(
        "write_test_file",
        {"attempt_id": a2.id, "path": target_path, "content": refl.fixed_content, "reason": refl.fix_reason},
    )
    frec2 = GeneratedTestFileRecord(
        attempt_id=a2.id,
        path=wout.path,
        content_text=refl.fixed_content,
        content_hash=wout.content_hash,
        previous_file_id=prev_file.id,
        generation_reason=refl.fix_reason,
    )
    ctx.recorder.add_generated_file(frec2)
    # case 元信息按 test_name 从上一版继承
    cases2 = _register_cases(ctx, frec2, {c.test_name: c for c in prev_cases})
    ctx.set_stage("reexecuting")
    out2 = do_run(ctx, a2, [frec2.path], cases2, plan_input.timeout_seconds)
    return out2, False


def _register_cases(ctx, frec, declared_by_name: dict) -> list[GeneratedTestCaseRecord]:
    recs: list[GeneratedTestCaseRecord] = []
    for p in parse_generated_cases(frec.content_text or ""):
        d = declared_by_name.get(p["test_name"])
        recs.append(
            GeneratedTestCaseRecord(
                file_id=frec.id,
                test_name=p["test_name"],
                start_line=p["start_line"],
                end_line=p["end_line"],
                nodeid=nodeid_for_case(frec.path, p),
                target_route=getattr(d, "target_route", None),
                target_function=getattr(d, "target_function", None),
                assertion_summary=getattr(d, "assertion_summary", None),
                source_strategy_version_id=ctx.strategy.id,
            )
        )
    ctx.recorder.add_generated_cases(recs)
    return recs


def _map_results(ctx, attempt, out: RunPytestOutput, attempt_cases) -> None:
    # 按 nodeid 对齐生成用例：参数化归并到父级 test_name；对不上标 unmatched
    by_nodeid = {base_nodeid(c.nodeid): c for c in attempt_cases if c.nodeid}
    by_name = {c.test_name: c for c in attempt_cases}
    fail_by_node = {f.nodeid: f for f in out.failures}
    recs = []
    for cr in out.case_results:
        gc = by_nodeid.get(base_nodeid(cr.nodeid)) or by_name.get(test_name_of(cr.nodeid))
        tb = fail_by_node.get(cr.nodeid)
        tb_hash = hashlib.sha256(tb.traceback.encode("utf-8")).hexdigest() if (tb and tb.traceback) else None
        recs.append(
            PytestCaseResultRecord(
                attempt_id=attempt.id,
                generated_test_case_id=(gc.id if gc else None),
                nodeid=cr.nodeid,
                mapping_status=("matched" if gc else "unmatched"),
                status=cr.status,
                duration_ms=cr.duration_ms,
                failure_type=cr.failure_type,
                failure_message=cr.message,
                traceback_hash=tb_hash,
            )
        )
    # 收集错误也落库（status=error, failure_type=collection/import），别让它们在记录里消失。
    # 但打 is_collection_error 标记：报告汇总收集成功率时要把它们摘出去，不算进 collected。
    for ce in out.collection_errors:
        recs.append(
            PytestCaseResultRecord(
                attempt_id=attempt.id,
                generated_test_case_id=None,
                nodeid=ce.nodeid or "<collect>",
                mapping_status="unmatched",
                status="error",
                failure_type=ce.failure_type,
                failure_message=ce.message,
                traceback_hash=hashlib.sha256(ce.traceback.encode("utf-8")).hexdigest() if ce.traceback else None,
                is_collection_error=True,
            )
        )
    ctx.recorder.add_pytest_results(recs)


def _as_draft(item) -> PlanItemDraft:
    if isinstance(item, PlanItemDraft):
        return item
    return PlanItemDraft(
        index=item.index,
        target_type=item.target_type,
        target_ref=item.target_ref,
        goal=item.goal,
        planned_assertions=item.planned_assertions,
    )


def _model_field_names(analysis) -> list[str]:
    names: list[str] = []
    for model in getattr(analysis, "models", []) or []:
        for field in getattr(model, "fields", []) or []:
            name = getattr(field, "name", None)
            if name:
                names.append(str(name))
    return names


def _should_reflect(out: RunPytestOutput) -> bool:
    # 有可修的测试问题才反思；系统级错误（超时/pytest 没起来）不反思
    if out.error:
        return False
    return out.failed > 0 or len(out.collection_errors) > 0


def _run_ok(out: RunPytestOutput) -> bool:
    # 真正成功：没系统错误、没失败、没收集错误、且确实收集到了用例
    return (not out.error) and out.failed == 0 and not out.collection_errors and out.collected > 0
