# 轻量 pytest 插件：把每个用例结果落成结构化 JSON，供 run_pytest 解析。
# 故意零依赖、不 import app，这样在任意子进程里 `-p _trace_pytest_plugin` 都能加载。
import json
import os

_results = {}        # nodeid -> 用例记录
_exc_types = {}      # nodeid -> 异常类型名（来自 excinfo）
_collect_errors = []  # 收集阶段失败（import 错误等）
_collected_count = 0  # 真实收集成功的测试项数 = len(session.items)


def _longrepr_text(report):
    lr = getattr(report, "longrepr", None)
    if lr is None:
        return None
    try:
        return str(lr)
    except Exception:
        return None


def pytest_exception_interact(node, call, report):
    # 这里能拿到真正的异常类型名，用来区分 AssertionError / ImportError / 其它
    nodeid = getattr(report, "nodeid", None) or getattr(node, "nodeid", "")
    excinfo = getattr(call, "excinfo", None)
    typename = getattr(excinfo, "typename", None)
    if nodeid and typename:
        _exc_types[nodeid] = typename


def pytest_runtest_logreport(report):
    nodeid = report.nodeid
    rec = _results.setdefault(nodeid, {"nodeid": nodeid, "duration": 0.0})
    rec["duration"] += getattr(report, "duration", 0.0) or 0.0

    if report.failed:
        # call 阶段失败 = 测试失败；setup/teardown 失败 = fixture/环境错误
        rec["outcome"] = "failed" if report.when == "call" else "error"
        rec["when_failed"] = report.when
        rec["longrepr"] = _longrepr_text(report)
        crash = getattr(getattr(report, "longrepr", None), "reprcrash", None)
        if crash is not None:
            rec["message"] = getattr(crash, "message", None)
            rec["file"] = getattr(crash, "path", None)
            rec["line"] = getattr(crash, "lineno", None)
    elif report.skipped:
        if rec.get("outcome") not in ("failed", "error"):
            rec["outcome"] = "skipped"
            rec["longrepr"] = _longrepr_text(report)
    elif report.when == "call":
        rec.setdefault("outcome", "passed")


def pytest_collectreport(report):
    if report.failed:
        _collect_errors.append(
            {"nodeid": report.nodeid or "<collect>", "longrepr": _longrepr_text(report)}
        )


def pytest_collection_finish(session):
    global _collected_count
    _collected_count = len(session.items)


def pytest_sessionfinish(session, exitstatus):
    path = os.environ.get("TRACE_PYTEST_REPORT")
    if not path:
        return
    for nodeid, rec in _results.items():
        if nodeid in _exc_types:
            rec["exc_type"] = _exc_types[nodeid]
    for ce in _collect_errors:
        if ce["nodeid"] in _exc_types:
            ce["exc_type"] = _exc_types[ce["nodeid"]]
    payload = {
        "exit_status": int(exitstatus),
        "collected": _collected_count,
        "cases": list(_results.values()),
        "collect_errors": _collect_errors,
    }
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        pass
