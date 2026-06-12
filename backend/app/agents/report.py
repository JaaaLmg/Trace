# 报告产出：从 recorder 汇总 metrics + 渲染 Markdown/JSON。报告链接到最终测试集结果与风险点。
from __future__ import annotations

import json
from pathlib import Path

from app.agents.final_attempts import final_attempts_from_records
from app.agents.runtime import AgentContext
from app.schemas.records import RunArtifactRecord, TestReportRecord


def build_report(ctx: AgentContext, *, suspected_code_bug: bool = False, artifacts_dir=None) -> TestReportRecord:
    rec = ctx.recorder
    run = ctx.run

    items = rec.list_plan_items(run.id)
    attempts = rec.list_attempts(run.id)
    all_results = rec.list_pytest_results(run.id)
    final_by_item = final_attempts_from_records(attempts, all_results)
    final_ids = {a.id for a in final_by_item.values()}

    final_results = [r for r in all_results if r.attempt_id in final_ids]
    # collected 只算真实收集成功的用例；收集期错误（import/collection）单独计数，
    # 绝不混进 collected——否则收集成功率被污染（对齐 M0 collected 语义）。
    real = [r for r in final_results if not getattr(r, "is_collection_error", False)]
    passed = sum(1 for r in real if r.status == "passed")
    failed = sum(1 for r in real if r.status in ("failed", "error"))
    skipped = sum(1 for r in real if r.status == "skipped")
    collected = len(real)
    collection_errors = len(final_results) - collected

    reflection_used = any(a.kind == "reflection" for a in attempts)
    contract_violation = any(a.error_code == "REFLECTION_CONTRACT_VIOLATION" for a in attempts)

    metrics = {
        "strategy_version_id": run.strategy_version_id,
        "workflow_type": ctx.strategy.workflow_type,
        "tool_call_count": run.tool_call_count,
        "total_tokens": run.total_tokens,
        "plan_items": len(items),
        "attempts": len(attempts),
        "reflection_used": reflection_used,
        "reflection_contract_violation": contract_violation,
        "suspected_code_bug": suspected_code_bug,
        "collected": collected,
        "collection_errors": collection_errors,
        "final_cases_total": collected,
        "final_passed": passed,
        "final_failed": failed,
        "final_skipped": skipped,
    }
    run.pytest_summary = {
        "collected": collected,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "collection_errors": collection_errors,
    }
    rec.save_run(run)

    risks = []
    if suspected_code_bug:
        risks.append("Reflection 判定疑似业务缺陷，已保留失败用例。")
    if contract_violation:
        risks.append("发生 Reflection 契约违规，对应修复未被采纳。")
    if collection_errors:
        risks.append(f"有 {collection_errors} 处测试文件收集失败（import/collection 错误）。")
    if failed:
        risks.append(f"最终仍有 {failed} 个用例失败/出错。")
    risk_notes = " ".join(risks) or "无显著风险。"

    summary = (
        f"{ctx.strategy.name}：生成 {collected} 个用例，通过 {passed}、失败 {failed}"
        + ("，已反思一次" if reflection_used else "")
    )
    report = TestReportRecord(run_id=run.id, summary=summary, metrics=metrics, risk_notes=risk_notes)

    if artifacts_dir:
        adir = Path(artifacts_dir) / run.id
        adir.mkdir(parents=True, exist_ok=True)
        md_path = adir / "report.md"
        json_path = adir / "report.json"
        md_path.write_text(_render_markdown(ctx, metrics, items, final_by_item, risk_notes), encoding="utf-8")
        json_path.write_text(
            json.dumps({"summary": summary, "metrics": metrics, "risk_notes": risk_notes}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        report.markdown_uri = str(md_path)
        report.json_uri = str(json_path)
        rec.add_artifact(RunArtifactRecord(run_id=run.id, artifact_type="report_md", uri=str(md_path)))
        rec.add_artifact(RunArtifactRecord(run_id=run.id, artifact_type="report_json", uri=str(json_path)))

    return report


def _render_markdown(ctx, metrics, items, final_by_item, risk_notes) -> str:
    run = ctx.run
    lines = [
        "# TRACE 测试报告",
        "",
        f"- Run: `{run.id}`",
        f"- 策略: {ctx.strategy.name} (`{ctx.strategy.workflow_type}`)",
        f"- 状态: {run.status}",
        f"- 工具调用: {metrics['tool_call_count']} | tokens: {metrics['total_tokens']}",
        f"- 反思: {'是' if metrics['reflection_used'] else '否'}"
        + ("（契约违规）" if metrics["reflection_contract_violation"] else ""),
        "",
        "## 用例结果（最终测试集）",
        "",
        f"通过 {metrics['final_passed']} / 失败 {metrics['final_failed']} / 跳过 {metrics['final_skipped']}"
        f"（共 {metrics['final_cases_total']}）",
        "",
        "## 任务拆分",
        "",
    ]
    for i in sorted(items, key=lambda x: x.index):
        fa = final_by_item.get(i.id)
        tail = f" → attempt#{fa.attempt_no}/{fa.kind}={fa.status}" if fa else ""
        lines.append(f"- [{i.status}] #{i.index} {i.goal}（{i.target_type}:{i.target_ref}）{tail}")
    lines += ["", "## 风险", "", risk_notes, ""]
    return "\n".join(lines)
