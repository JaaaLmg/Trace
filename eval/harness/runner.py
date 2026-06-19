# 评测 runner：单次「干净生成 + 全变体重放」。
# 污染隔离：生成阶段 Agent 的 root 钉在干净副本（read/analyze 白名单限制在 root 内，物理上看不到变体/ground truth）；
# 变体在独立目录由 clean+patch 现做；重放只拷测试内容，不重新生成。
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.agents.orchestrator import execute_run
from app.agents.recorder import InMemoryRecorder
from app.agents.runtime import PlanInput
from app.tools import default_registry
from app.tools.base import ToolContext

from eval.harness import dataset
from eval.harness.final_set import final_test_set
from eval.harness.probes import check_variant_probe
from eval.harness.replay import replay

GOAL = "为 shop 模块生成 pytest 测试，覆盖定价函数与价格查询路由"


@dataclass
class CleanRun:
    strategy_id: str
    strategy_name: str
    repeat: int
    status: str
    files: dict
    clean_passed: set
    clean_failed: bool
    n_cases: int
    tokens: int
    tool_calls: int
    reflection_used: bool
    error_code: str | None = None
    error_message: str | None = None
    variants: dict = field(default_factory=dict)  # bug_id -> {captured, capturing_tests, bug_type, target}


def run_clean(strategy_spec, make_llm, repeat: int, workdir: Path) -> CleanRun:
    clean_root = dataset.materialize_clean(Path(workdir) / "clean")
    ctx = ToolContext(root=clean_root, test_write_dir=clean_root / "tests" / "generated")
    rec = InMemoryRecorder()
    llm = make_llm()
    try:
        outcome = execute_run(
            tools=ctx,
            registry=default_registry(),
            llm=llm,
            recorder=rec,
            strategy_spec=strategy_spec,
            plan_input=PlanInput(target_scope=[], goal=GOAL, allow_reflection=True),
            artifacts_dir=Path(workdir) / "artifacts",
        )
    finally:
        # 真实 LLM 用完关 httpx 连接，别让每个 run 泄漏一个 client；MockLLM 无 close，跳过
        close = getattr(llm, "close", None)
        if close:
            close()
    fts = final_test_set(rec, outcome.run)
    m = outcome.report.metrics if outcome.report else {}
    return CleanRun(
        strategy_id=strategy_spec.id,
        strategy_name=strategy_spec.name,
        repeat=repeat,
        status=outcome.run.status,
        files=fts.files,
        clean_passed=fts.clean_passed,
        clean_failed=fts.clean_failed,
        n_cases=fts.n_cases,
        tokens=outcome.run.total_tokens,
        tool_calls=outcome.run.tool_call_count,
        reflection_used=bool(m.get("reflection_used")),
        error_code=outcome.run.error_code,
        error_message=outcome.run.error_message,
    )


def evaluate_variants(clean: CleanRun, bugs, workdir: Path) -> None:
    """对每个 in-scope 变体重放干净测试集，判定是否捕获，写回 clean.variants。"""
    for bug in bugs:
        var_root = dataset.materialize_variant(bug, Path(workdir) / f"variant_{bug.id}")
        probe_check = check_variant_probe(
            clean_root=dataset.CLEAN_ROOT,
            variant_root=var_root,
            ground_truth={
                "target_kind": bug.kind,
                "probe": bug.probe,
                "clean_value": bug.clean_value,
                "buggy_value": bug.buggy_value,
                "patch_artifact": {"patch": {"file": bug.file}},
            },
            variant_id=bug.id,
        )
        out = replay(var_root, clean.files)
        # 捕获判定（系统设计 §11.1）：同一测试在干净通过、在变体上 assertion failure。
        # 失败相关性由实验设计保证：变体只改一处，测试内容不变 → 行为差异必由该 patch 引起。
        capturing = [
            cr.nodeid
            for cr in out.case_results
            if cr.nodeid in clean.clean_passed and cr.status == "failed" and cr.failure_type == "assertion"
        ]
        clean.variants[bug.id] = {
            "captured": bool(capturing),
            "capturing_tests": capturing,
            "bug_type": bug.bug_type,
            "target": bug.target,
            "probe_check": probe_check,
        }


def run_one(strategy_spec, make_llm, repeat: int, workdir: Path, bugs) -> CleanRun:
    clean = run_clean(strategy_spec, make_llm, repeat, workdir)
    if clean.status != "completed":
        return clean
    evaluate_variants(clean, bugs, workdir)
    return clean
