# 评测 harness 端到端 + 指标聚合自测。
# 端到端跑真 pytest 子进程：干净生成 → 6 变体重放，验证三策略的捕获/假阳性/反思故事。
# 聚合用合成数据快测，证明 3 次重复的均值/标准差/假阳性/成本口径，无需起子进程。
from __future__ import annotations

from eval.harness import metrics
from eval.harness.run_eval import _format_run_error, run_full_eval
from eval.harness.runner import CleanRun


def test_full_eval_story(tmp_path):
    result = run_full_eval(tmp_path, repeats=1)
    rows = {r["strategy_id"]: r for r in result["rows"]}

    # Direct：单发把路由测试状态码写反 → 干净上失败=假阳性；且漏掉 wrong-status（5/6）
    d = rows["sv-direct-v1"]
    assert d["false_positive_rate"] == 1.0
    assert d["reflection_used"] is False
    assert abs(d["capture_rate_mean"] - 5 / 6) < 1e-9

    # Plan-and-Execute：逐目标，路由写对，全捕获、无假阳性
    p = rows["sv-plan-v1"]
    assert abs(p["capture_rate_mean"] - 1.0) < 1e-9
    assert p["false_positive_rate"] == 0.0

    # ReAct+Reflection：反思把路由断言修回 404 → 全捕获、无假阳性、用了反思
    re = rows["sv-react-v1"]
    assert abs(re["capture_rate_mean"] - 1.0) < 1e-9
    assert re["false_positive_rate"] == 0.0
    assert re["reflection_used"] is True

    # 对比表 + 捕获矩阵渲染出来；wrong-status 被 plan/react 抓到、被 direct 漏掉
    assert "捕获率" in result["table_md"]
    assert "wrong-status" in result["matrix_md"]
    m = result["capture_matrix"]
    assert m["wrong-status"]["sv-plan-v1"] is True
    assert m["wrong-status"]["sv-react-v1"] is True
    assert m["wrong-status"]["sv-direct-v1"] is False


def _mk(sid, rep, captured_ids, clean_failed, tokens, all_ids):
    variants = {bid: {"captured": bid in captured_ids} for bid in all_ids}
    return CleanRun(
        strategy_id=sid, strategy_name=sid, repeat=rep, status="completed",
        files={}, clean_passed=set(), clean_failed=clean_failed, n_cases=0,
        tokens=tokens, tool_calls=3, reflection_used=False, variants=variants,
    )


def test_aggregate_repeat_stats():
    ids = [f"b{i}" for i in range(6)]
    # 三次重复捕获数 6/4/5 → 率 1.0/0.667/0.833，均值 0.833、std>0；一次干净失败 → 假阳性 1/3
    runs = [
        _mk("s", 0, ids[:6], False, 100, ids),
        _mk("s", 1, ids[:4], True, 100, ids),
        _mk("s", 2, ids[:5], False, 100, ids),
    ]
    [row] = metrics.aggregate({"s": runs}, total_in_scope=6)
    assert abs(row["capture_rate_mean"] - (1.0 + 4 / 6 + 5 / 6) / 3) < 1e-9
    assert row["capture_rate_std"] > 0  # 重复间有差异，标准差非零
    assert abs(row["false_positive_rate"] - 1 / 3) < 1e-9
    assert row["cost_per_captured_bug"] == 300 / 15  # total_tokens / total_captured

    # 0 捕获：成本记 None（no_bug_captured），不用 0 伪装
    zero = [_mk("z", 0, [], False, 50, ids)]
    [zrow] = metrics.aggregate({"z": zero}, total_in_scope=6)
    assert zrow["cost_per_captured_bug"] is None


def test_format_run_error_keeps_smoke_failure_actionable():
    run = _mk("s", 0, [], False, 0, ["b0"])
    run.status = "failed"
    run.error_code = "LLM_PROVIDER_ERROR"
    run.error_message = "OpenAI API HTTP 401 Unauthorized: bad key"

    assert _format_run_error(run) == "LLM_PROVIDER_ERROR: OpenAI API HTTP 401 Unauthorized: bad key"
