# 最终 attempt 选择口径：每个 plan item 取最后一次真正跑出 pytest 结果的 attempt。
from __future__ import annotations


def final_attempts_by_item(rec, run_id) -> dict:
    """返回 run 内每个 plan item 的最终 attempt，供报告和 eval 重放共用同一口径。"""
    items = [i for i in getattr(rec, "plan_items", []) if i.run_id == run_id]
    item_ids = {i.id for i in items}
    attempts = [a for a in getattr(rec, "attempts", {}).values() if a.run_plan_item_id in item_ids]

    res_by_attempt: dict = {}
    for r in getattr(rec, "pytest_results", []):
        res_by_attempt.setdefault(r.attempt_id, []).append(r)

    by_item: dict = {}
    for a in attempts:
        by_item.setdefault(a.run_plan_item_id, []).append(a)

    final: dict = {}
    for item_id, alist in by_item.items():
        with_res = [a for a in alist if a.id in res_by_attempt]
        pool = with_res or alist
        final[item_id] = max(pool, key=lambda a: a.attempt_no)
    return final


def final_attempt_ids(rec, run_id) -> set:
    return {a.id for a in final_attempts_by_item(rec, run_id).values()}
