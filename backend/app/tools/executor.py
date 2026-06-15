from __future__ import annotations

import json
import os
import shlex
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

    V2 §10.1：pytest 命令要来自 runtime snapshot。这里的 python 解释器和「用户可控的
    pytest 参数」（-q/-k/-m 等）由 runtime profile 的 test_command 驱动；但结构性参数
    （trace 插件、--rootdir、关缓存、junit、屏蔽 addopts）始终由执行器强制注入，
    否则结构化报告和跨 run 的 nodeid 对齐会坏。
    """

    def __init__(self, *, python_executable: str | None = None, extra_pytest_args: Optional[list[str]] = None):
        self.python_executable = python_executable or sys.executable
        self.extra_pytest_args = list(extra_pytest_args or [])

    def _build_cmd(self, work_dir: Path, junit_path: Path, test_paths: list[str]) -> list[str]:
        cmd = [
            self.python_executable, "-m", "pytest",
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
        ]
        # 保底的 -q/--no-header；若 profile 的 test_command 已带就不重复。
        for default_arg in ("-q", "--no-header"):
            if default_arg not in self.extra_pytest_args:
                cmd.append(default_arg)
        cmd += self.extra_pytest_args
        cmd += [f"--junitxml={junit_path}", *test_paths]
        return cmd

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

        cmd = self._build_cmd(work_dir, junit_path, test_paths)
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


# 从 test_command 里安全透传的 pytest 参数：只放选择/详略类，不放会破坏结构化报告或
# nodeid 对齐的结构性参数（那些由执行器强制注入）。
_PASSTHROUGH_FLAGS = {"-q", "--quiet", "--no-header", "-x", "-ra", "-rA", "-s", "-v", "-vv"}
_PASSTHROUGH_VALUE_FLAGS = {"-k", "-m", "--maxfail", "--tb"}


def _parse_test_command(test_command: str | None) -> tuple[str | None, list[str]]:
    """从 runtime profile 的 test_command 解析出（解释器路径, 透传 pytest 参数）。

    - 解释器：只有显式带路径分隔符（如 venv/conda 的绝对路径）才采用；裸 `python` 退回
      `sys.executable`，因为 python_version 字符串无法安全映射成可执行文件。
    - 参数：只取允许清单内的选择/详略类参数，其余忽略（执行器自注入结构性参数）。
    """
    try:
        tokens = shlex.split(test_command or "", posix=False)
    except ValueError:
        return None, []
    tokens = [_strip_outer_quotes(token) for token in tokens]
    if not tokens:
        return None, []

    pytest_idx = next((i for i, t in enumerate(tokens) if t == "pytest" or t.endswith(("/pytest", "\\pytest"))), None)
    interpreter = None
    if pytest_idx is not None and pytest_idx >= 1:
        candidate = tokens[0]
        if "/" in candidate or "\\" in candidate:
            interpreter = candidate

    region = tokens[pytest_idx + 1:] if pytest_idx is not None else tokens
    extra: list[str] = []
    i = 0
    while i < len(region):
        tok = region[i]
        if tok in _PASSTHROUGH_FLAGS:
            extra.append(tok)
        elif tok in _PASSTHROUGH_VALUE_FLAGS:
            extra.append(tok)
            if i + 1 < len(region):
                extra.append(region[i + 1])
                i += 1
        elif "=" in tok and tok.split("=", 1)[0] in _PASSTHROUGH_VALUE_FLAGS:
            extra.append(tok)
        i += 1
    return interpreter, extra


def _strip_outer_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def executor_from_runtime_snapshot(snapshot: dict | None) -> LocalSubprocessExecutor:
    """按冻结的 runtime snapshot 构造执行器，让 pytest 命令真正来自 snapshot（V2 §10.1）。"""
    test_command = (snapshot or {}).get("test_command") if snapshot else None
    interpreter, extra = _parse_test_command(test_command)
    return LocalSubprocessExecutor(python_executable=interpreter, extra_pytest_args=extra)
