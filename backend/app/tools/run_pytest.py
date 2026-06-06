from __future__ import annotations

from app.schemas.tools import (
    ArtifactRef,
    CaseResult,
    FailureDetail,
    RunPytestInput,
    RunPytestOutput,
)
from app.tools.base import ToolContext
from app.tools.executor import LocalSubprocessExecutor, PytestExecutor


def run_pytest(ctx: ToolContext, inp: RunPytestInput) -> RunPytestOutput:
    """执行 + 把原始结果解析成结构化契约。执行交给注入的 executor，解析是 A 的活。"""
    executor: PytestExecutor = ctx.executor or LocalSubprocessExecutor()
    # P1 白名单：每个 test_path canonical 校验到 test_write_dir 内，再转相对 root 给执行器
    safe_paths = _safe_test_paths(ctx, inp.test_paths)
    raw = executor.run(ctx.root, safe_paths, inp.timeout_seconds)

    if raw.timed_out:
        return RunPytestOutput(exit_code=-1, error=f"pytest 超时（>{inp.timeout_seconds}s）")

    if raw.report is None:
        # 插件没产出报告：pytest 没起来 / 进程异常
        return RunPytestOutput(
            exit_code=raw.exit_code,
            error=_short(raw.stderr or raw.stdout) or "pytest 未产出结构化报告",
        )

    case_results: list[CaseResult] = []
    failures: list[FailureDetail] = []
    passed = failed = skipped = 0

    for c in raw.report.get("cases", []):
        status = c.get("outcome", "passed")
        ftype = _classify(c) if status in ("failed", "error") else None
        case_results.append(
            CaseResult(
                nodeid=c["nodeid"],
                status=status,
                duration_ms=int((c.get("duration") or 0.0) * 1000),
                message=_short(c.get("message")),
                failure_type=ftype,
                when_failed=c.get("when_failed"),
                exc_type=c.get("exc_type"),
            )
        )
        if status == "passed":
            passed += 1
        elif status == "skipped":
            skipped += 1
        else:
            failed += 1
            failures.append(
                FailureDetail(
                    nodeid=c["nodeid"],
                    file=c.get("file"),
                    line=c.get("line"),
                    exc_type=c.get("exc_type"),
                    message=_short(c.get("message")),
                    traceback=_short(c.get("longrepr"), 4000),
                    failure_type=ftype,
                )
            )

    # P2：收集错误独立成类，绝不算进 collected / case_results / failed，否则收集成功率等指标会脏
    collection_errors: list[FailureDetail] = []
    for ce in raw.report.get("collect_errors", []):
        exc = ce.get("exc_type") or ""
        lr = ce.get("longrepr") or ""
        is_import = exc in ("ModuleNotFoundError", "ImportError") or "ModuleNotFoundError" in lr or "ImportError" in lr
        collection_errors.append(
            FailureDetail(
                nodeid=ce.get("nodeid") or "<collect>",
                exc_type=ce.get("exc_type"),
                message=_short(lr),
                traceback=_short(lr, 4000),
                failure_type="import" if is_import else "collection",
            )
        )

    artifacts: list[ArtifactRef] = []
    junit = ctx.root / ".trace_junit.xml"
    if junit.exists():
        artifacts.append(ArtifactRef(type="junit_xml", uri=ctx.relpath(junit)))

    return RunPytestOutput(
        exit_code=raw.exit_code,
        collected=int(raw.report.get("collected", 0)),  # 真实收集数，来自 session.items
        passed=passed,
        failed=failed,
        skipped=skipped,
        duration_ms=raw.duration_ms,
        case_results=case_results,
        failures=failures,
        collection_errors=collection_errors,
        artifacts=artifacts,
    )


def _safe_test_paths(ctx: ToolContext, test_paths: list[str]) -> list[str]:
    if not test_paths:
        # 没给路径就只跑生成测试目录，绝不退化成跑整个项目根
        return [ctx.relpath(ctx.test_write_dir)]
    safe: list[str] = []
    for tp in test_paths:
        # resolve_write 做 canonical 校验：越界 / 想跑 test_write_dir 外的代码 → TOOL_ARGUMENT_ERROR
        safe.append(ctx.relpath(ctx.resolve_write(tp)))
    return safe


def _classify(c: dict) -> str:
    # 评测捕获率只认 assertion；fixture/import/其它 error 都不算抓到 bug
    if c.get("when_failed") in ("setup", "teardown"):
        return "fixture"
    exc = c.get("exc_type") or ""
    if exc == "AssertionError":
        return "assertion"
    if exc in ("ModuleNotFoundError", "ImportError"):
        return "import"
    return "error"


def _short(text, limit: int = 600):
    if not text:
        return None
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "…[截断]"
