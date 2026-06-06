from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol


@dataclass
class RawPytestRun:
    """执行器的原始产出：退出码 + 日志 + 插件结构化报告。解析成契约由 run_pytest 负责。"""

    exit_code: int
    stdout: str
    stderr: str
    report: Optional[dict]  # 来自 _trace_pytest_plugin 的 JSON；None = 没产出
    duration_ms: int
    timed_out: bool = False


class PytestExecutor(Protocol):
    """执行器端口。A 定接口，B 后续换成 venv + 路径白名单 + 禁网的加固版。"""

    def run(
        self, work_dir: Path, test_paths: list[str], timeout_seconds: int
    ) -> RawPytestRun: ...


_PLUGIN_DIR = Path(__file__).resolve().parent
_PLUGIN_NAME = "_trace_pytest_plugin"


class LocalSubprocessExecutor:
    """V1 最简执行器：独立 subprocess + 独立工作目录 + 硬超时。

    口径红线（V1实施清单 §4）：跑的是 LLM 生成的任意 Python，
    subprocess + 白名单不是安全沙箱。真正的容器隔离是 B 在 V2 做。
    """

    def run(
        self, work_dir: Path, test_paths: list[str], timeout_seconds: int
    ) -> RawPytestRun:
        work_dir = Path(work_dir).resolve()
        report_path = work_dir / ".trace_pytest_report.json"
        junit_path = work_dir / ".trace_junit.xml"
        for p in (report_path, junit_path):
            if p.exists():
                p.unlink()

        env = os.environ.copy()
        env["TRACE_PYTEST_REPORT"] = str(report_path)
        # 让子进程能 import 到结构化插件 + 被测项目本身
        parts = [str(_PLUGIN_DIR), str(work_dir), env.get("PYTHONPATH", "")]
        env["PYTHONPATH"] = os.pathsep.join(p for p in parts if p)
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        cmd = [
            sys.executable, "-m", "pytest",
            "-p", _PLUGIN_NAME,
            # 关掉 pytest 缓存：执行器跑的都是一次性 work_dir，缓存零收益；评测会反复物化/删除
            # 这些目录，别让 .pytest_cache 写进去，否则 Windows 下次 rmtree 容易被刚释放的缓存
            # 目录句柄卡住（access denied）。
            "-p", "no:cacheprovider",
            # 把 rootdir 钉在 work_dir：否则若 work_dir 落在某个带 pyproject/pytest.ini 的项目下，
            # pytest 会把 rootdir 设到那个祖先目录，nodeid 变成相对祖先的路径 → 同一份测试在
            # 不同 work_dir（如干净 vs bug 变体）下 nodeid 不一致，评测重放的跨 run 对齐就废了。
            "--rootdir", str(work_dir),
            "-o", "addopts=",  # 屏蔽被测项目自带的 addopts（如强制 coverage）
            "-q", "--no-header",
            f"--junitxml={junit_path}",
            *test_paths,
        ]
        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd, cwd=str(work_dir), env=env,
                capture_output=True, text=True, timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as e:
            dur = int((time.monotonic() - start) * 1000)
            return RawPytestRun(
                exit_code=-1,
                stdout=_as_text(e.stdout), stderr=_as_text(e.stderr),
                report=None, duration_ms=dur, timed_out=True,
            )

        dur = int((time.monotonic() - start) * 1000)
        report = None
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except Exception:
                report = None
        return RawPytestRun(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr,
            report=report, duration_ms=dur,
        )


def _as_text(v) -> str:
    if v is None:
        return ""
    return v if isinstance(v, str) else v.decode("utf-8", errors="replace")
