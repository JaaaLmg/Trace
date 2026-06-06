# 从一次「干净代码」run 里抽出「最终测试集」，供变体重放用。
# 最终测试集 = 每个任务最后一次「真跑出结果」的 attempt 的测试文件（反思后通过的那版）。
# 口径与 report.build_report 的 final_by_item 一致：反思被拒/疑似缺陷时回退到首轮，不取空 attempt。
from __future__ import annotations

from dataclasses import dataclass

from app.agents.final_attempts import final_attempt_ids


@dataclass
class FinalTestSet:
    files: dict  # relpath -> content（重放时按原路径写回变体目录，保证 nodeid 一致）
    clean_passed: set  # 在干净代码上通过的 nodeid
    clean_failed: bool  # 干净代码上是否存在失败/出错用例（假阳性判定）
    n_cases: int  # 干净最终测试集里的真实用例数（不含收集错误）


def final_test_set(rec, run) -> FinalTestSet:
    final_ids = final_attempt_ids(rec, run.id)

    files: dict = {}
    for f in getattr(rec, "files", []):
        if f.attempt_id in final_ids:
            files[f.path] = f.content_text or ""

    passed: set = set()
    n_cases = 0
    clean_failed = False
    for r in getattr(rec, "pytest_results", []):
        if r.attempt_id not in final_ids or getattr(r, "is_collection_error", False):
            continue
        n_cases += 1
        if r.status == "passed":
            passed.add(r.nodeid)
        elif r.status in ("failed", "error"):
            clean_failed = True
    # 收集错误也算干净侧异常（假阳性/不健康）
    if any(
        getattr(r, "is_collection_error", False) and r.attempt_id in final_ids
        for r in getattr(rec, "pytest_results", [])
    ):
        clean_failed = True

    return FinalTestSet(files=files, clean_passed=passed, clean_failed=clean_failed, n_cases=n_cases)
