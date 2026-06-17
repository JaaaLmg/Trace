# 指标聚合 + 对比表渲染。口径对齐 系统设计 §11：
#   seeded_bug_capture_rate = captured_in_scope / total_in_scope（按重复取均值 ± 总体标准差）
#   clean_false_positive_rate = clean_failed_runs / clean_total_runs
#   cost_per_captured_bug = total_tokens / total_captured（0 捕获时记 no_bug_captured，不用 0 伪装）
from __future__ import annotations

import statistics


def _captured_count(clean_run) -> int:
    return sum(1 for v in clean_run.variants.values() if v["captured"])


def aggregate(runs_by_strategy: dict, total_in_scope: int) -> list[dict]:
    rows = []
    for sid, runs in runs_by_strategy.items():
        invalid_test_sets = sum(1 for r in runs if getattr(r, "invalid_test_set", False))
        evaluable_runs = [r for r in runs if not getattr(r, "invalid_test_set", False)]
        metric_status = "invalid_test_set" if runs and not evaluable_runs else "ok"
        caps = [_captured_count(r) for r in evaluable_runs]
        rates = [(c / total_in_scope if total_in_scope else 0.0) for c in caps]
        tokens = [r.tokens for r in evaluable_runs]
        tool_calls = [r.tool_calls for r in evaluable_runs]
        n = len(evaluable_runs) or 1
        total_captured = sum(caps)
        total_tokens = sum(tokens)
        if metric_status == "ok" and total_captured == 0:
            metric_status = "evaluable_zero_capture"
        rows.append(
            {
                "strategy_id": sid,
                "strategy_name": runs[0].strategy_name if runs else sid,
                "repeats": len(evaluable_runs),
                "captured_per_repeat": caps,
                "captured_mean": statistics.mean(caps) if caps else 0.0,
                "total_in_scope": total_in_scope,
                "capture_rate_mean": statistics.mean(rates) if rates else 0.0,
                "capture_rate_std": statistics.pstdev(rates) if rates else 0.0,
                "false_positive_rate": sum(1 for r in evaluable_runs if r.clean_failed) / n,
                "avg_tokens": statistics.mean(tokens) if tokens else 0.0,
                "avg_tool_calls": statistics.mean(tool_calls) if tool_calls else 0.0,
                "reflection_used": any(r.reflection_used for r in evaluable_runs),
                "invalid_test_set_count": invalid_test_sets,
                "metric_status": metric_status,
                # 0 捕获时不要用 0 伪装成本（§11.1）
                "cost_per_captured_bug": (total_tokens / total_captured) if total_captured else None,
            }
        )
    return rows


def capture_matrix(runs_by_strategy: dict, bugs) -> dict:
    # bug_id -> {strategy_id: 任一重复捕获即 True}
    matrix: dict = {}
    for bug in bugs:
        matrix[bug.id] = {
            sid: any(r.variants.get(bug.id, {}).get("captured") for r in runs)
            for sid, runs in runs_by_strategy.items()
        }
    return matrix


def comparison_table_md(rows: list[dict]) -> str:
    lines = [
        "| 策略 | 捕获率(均值±std) | 假阳性率 | 反思 | 平均 token | 平均工具调用 | cost/captured |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        cap = f"{r['capture_rate_mean']:.2f} ± {r['capture_rate_std']:.2f}（{r['captured_mean']:.1f}/{r['total_in_scope']}）"
        cost = "no_bug_captured" if r["cost_per_captured_bug"] is None else f"{r['cost_per_captured_bug']:.1f}"
        lines.append(
            f"| {r['strategy_name']} | {cap} | {r['false_positive_rate']:.2f} | "
            f"{'是' if r['reflection_used'] else '否'} | {r['avg_tokens']:.0f} | {r['avg_tool_calls']:.1f} | {cost} |"
        )
    return "\n".join(lines)


def capture_matrix_md(matrix: dict, bugs, runs_by_strategy: dict) -> str:
    sids = list(runs_by_strategy)
    names = {sid: (runs[0].strategy_name if runs else sid) for sid, runs in runs_by_strategy.items()}
    bug_type = {b.id: b.bug_type for b in bugs}
    header = "| bug | 类型 | " + " | ".join(names[s] for s in sids) + " |"
    sep = "| --- | --- | " + " | ".join("---" for _ in sids) + " |"
    lines = [header, sep]
    for b in bugs:
        cells = " | ".join("✓" if matrix[b.id][s] else "✗" for s in sids)
        lines.append(f"| {b.id} | {bug_type[b.id]} | {cells} |")
    return "\n".join(lines)
