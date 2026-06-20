from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol


@dataclass
class RawPytestRun:
    """执行器的原始产出：退出码 + 日志 + 插件结构化报告。解析成契约由 run_pytest 负责。"""

    exit_code: int
    stdout: str
    stderr: str
    report: Optional[dict]  # 来自 _trace_pytest_plugin 的 JSON；None = 没产出
    duration_ms: int
    timed_out: bool = False
    executor_metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ExecutorWorkspace:
    host_path: Path
    container_path: str | None
    strategy: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ExecutorSetupResult:
    status: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ExecutorCapabilities:
    executor_kind: str
    isolation_level: str
    network_enforced: bool
    resource_limits_enforced: bool
    workspace_strategy: str
    supports_parallel: bool
    policy_notes: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "executor_kind": self.executor_kind,
            "isolation_level": self.isolation_level,
            "network_enforced": self.network_enforced,
            "resource_limits_enforced": self.resource_limits_enforced,
            "workspace_strategy": self.workspace_strategy,
            "supports_parallel": self.supports_parallel,
            "policy_notes": list(self.policy_notes),
        }


class PytestExecutor(Protocol):
    """执行器端口。A 定接口，B 后续换成 venv + 路径白名单 + 禁网的加固版。"""

    def prepare_workspace(self, work_dir: Path) -> ExecutorWorkspace: ...

    def run_setup(self, work_dir: Path, install_command: str | None, timeout_seconds: int) -> ExecutorSetupResult: ...

    def run(
        self, work_dir: Path, test_paths: list[str], timeout_seconds: int
    ) -> RawPytestRun: ...

    def collect_artifacts(self, work_dir: Path) -> dict[str, Any]: ...

    def cleanup_workspace(self, workspace: ExecutorWorkspace) -> dict[str, Any]: ...

    def capabilities(self) -> ExecutorCapabilities: ...


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

    def capabilities(self) -> ExecutorCapabilities:
        return ExecutorCapabilities(
            executor_kind="local_subprocess",
            isolation_level="process",
            network_enforced=False,
            resource_limits_enforced=False,
            workspace_strategy="host_workdir",
            supports_parallel=True,
            policy_notes=[
                "Runs pytest in a local subprocess.",
                "This executor is not a security sandbox.",
                "network_policy and resource_limits are recorded but not strongly enforced.",
            ],
        )

    def prepare_workspace(self, work_dir: Path) -> ExecutorWorkspace:
        return ExecutorWorkspace(
            host_path=Path(work_dir).resolve(),
            container_path=None,
            strategy=self.capabilities().workspace_strategy,
            metadata={"executor": "local_subprocess"},
        )

    def run_setup(self, work_dir: Path, install_command: str | None, timeout_seconds: int) -> ExecutorSetupResult:
        if not install_command:
            return ExecutorSetupResult(status="skipped", metadata={"reason": "no install_command"})
        try:
            proc = subprocess.run(
                str(install_command),
                cwd=str(Path(work_dir).resolve()),
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return ExecutorSetupResult(
                status="failed",
                exit_code=-1,
                stdout=_as_text(exc.stdout),
                stderr=_as_text(exc.stderr),
                metadata={"timed_out": True},
            )
        return ExecutorSetupResult(
            status="completed" if proc.returncode == 0 else "failed",
            exit_code=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            metadata={"timed_out": False},
        )

    def collect_artifacts(self, work_dir: Path) -> dict[str, Any]:
        work_dir = Path(work_dir).resolve()
        return {
            "pytest_json": str(work_dir / ".trace_pytest_report.json"),
            "junit_xml": str(work_dir / ".trace_junit.xml"),
        }

    def cleanup_workspace(self, workspace: ExecutorWorkspace) -> dict[str, Any]:
        return {"status": "not_applicable", "workspace": str(workspace.host_path)}

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
            executor_metadata={
                "executor": self.capabilities().as_dict(),
                "command": cmd,
                "work_dir": str(work_dir),
            },
        )


class DockerExecutorUnavailable(RuntimeError):
    pass


class DockerPytestExecutor:
    """Opt-in Docker pytest executor.

    This is intentionally conservative: TRACE still prepares a per-run workspace
    outside the container, then Docker executes pytest inside that workspace with
    the TRACE pytest plugin mounted read-only.
    """

    def __init__(
        self,
        *,
        image: str,
        extra_pytest_args: Optional[list[str]] = None,
        network_policy: str = "default",
        resource_limits: dict[str, Any] | None = None,
        env_template: dict[str, Any] | None = None,
        working_dir: str = "/workspace",
        pull_policy: str = "if_missing",
        cleanup_policy: dict[str, Any] | None = None,
    ):
        if not image:
            raise DockerExecutorUnavailable("docker executor requires an image")
        self.image = image
        self.extra_pytest_args = list(extra_pytest_args or [])
        self.network_policy = network_policy
        self.resource_limits = dict(resource_limits or {})
        self.env_template = dict(env_template or {})
        self.working_dir = working_dir or "/workspace"
        self.pull_policy = pull_policy or "if_missing"
        self.cleanup_policy = dict(cleanup_policy or {})

    def capabilities(self) -> ExecutorCapabilities:
        return ExecutorCapabilities(
            executor_kind="docker",
            isolation_level="container",
            network_enforced=True,
            resource_limits_enforced=True,
            workspace_strategy="bind_mount_workspace",
            supports_parallel=True,
            policy_notes=[
                "Runs pytest in a Docker container.",
                "Workspace is mounted into the container and TRACE pytest plugin is mounted read-only.",
            ],
        )

    def prepare_workspace(self, work_dir: Path) -> ExecutorWorkspace:
        return ExecutorWorkspace(
            host_path=Path(work_dir).resolve(),
            container_path=self.working_dir,
            strategy=self.capabilities().workspace_strategy,
            metadata={
                "executor": "docker",
                "image": self.image,
                "workspace_mount": {"host_path": str(Path(work_dir).resolve()), "container_path": self.working_dir},
            },
        )

    def run_setup(self, work_dir: Path, install_command: str | None, timeout_seconds: int) -> ExecutorSetupResult:
        if not install_command:
            return ExecutorSetupResult(status="skipped", metadata={"reason": "no install_command"})
        if self.network_policy == "disabled":
            network_args = ["--network", "none"]
        else:
            network_args = []
        setup_cmd = [
            "docker", "run", "--rm",
            *network_args,
            "-v", f"{str(Path(work_dir).resolve())}:{self.working_dir}",
            "-w", self.working_dir,
            self.image,
            "sh", "-lc", str(install_command),
        ]
        self._ensure_image()
        try:
            proc = subprocess.run(setup_cmd, capture_output=True, text=True, timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            return ExecutorSetupResult(
                status="failed",
                exit_code=-1,
                stdout=_as_text(exc.stdout),
                stderr=_as_text(exc.stderr),
                metadata={"command": setup_cmd, "timed_out": True},
            )
        return ExecutorSetupResult(
            status="completed" if proc.returncode == 0 else "failed",
            exit_code=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            metadata={"command": setup_cmd, "timed_out": False},
        )

    def collect_artifacts(self, work_dir: Path) -> dict[str, Any]:
        work_dir = Path(work_dir).resolve()
        return {
            "pytest_json": str(work_dir / ".trace_pytest_report.json"),
            "junit_xml": str(work_dir / ".trace_junit.xml"),
            "stdout_stderr": "captured in executor metadata",
        }

    def cleanup_workspace(self, workspace: ExecutorWorkspace) -> dict[str, Any]:
        return {
            "status": "auto" if self.cleanup_policy.get("keep_container") is not True else "manual",
            "workspace": str(workspace.host_path),
        }

    def _build_pytest_args(self, junit_path: str, test_paths: list[str]) -> list[str]:
        cmd = [
            "python", "-m", "pytest",
            "-p", _PLUGIN_NAME,
            "-p", "no:cacheprovider",
            "--rootdir", self.working_dir,
            "-o", "addopts=",
        ]
        for default_arg in ("-q", "--no-header"):
            if default_arg not in self.extra_pytest_args:
                cmd.append(default_arg)
        cmd += self.extra_pytest_args
        cmd += [f"--junitxml={junit_path}", *test_paths]
        return cmd

    def _docker_run_cmd(self, work_dir: Path, test_paths: list[str]) -> list[str]:
        junit_path = f"{self.working_dir}/.trace_junit.xml"
        container_name = f"trace-pytest-{uuid.uuid4().hex[:12]}"
        keep_container = self.cleanup_policy.get("keep_container") is True
        cmd = ["docker", "run"]
        if not keep_container:
            cmd.append("--rm")
        cmd += [
            "--name", container_name,
            "--label", "trace.executor=pytest",
            "--label", "trace.cleanup=manual" if keep_container else "trace.cleanup=auto",
        ]
        if self.network_policy in {"disabled", "install_only"}:
            cmd += ["--network", "none"]
        memory = self.resource_limits.get("memory") or self.resource_limits.get("memory_limit")
        cpus = self.resource_limits.get("cpus") or self.resource_limits.get("cpu")
        if memory:
            cmd += ["--memory", str(memory)]
        if cpus:
            cmd += ["--cpus", str(cpus)]
        cmd += [
            "-v", f"{str(work_dir)}:{self.working_dir}",
            "-v", f"{str(_PLUGIN_DIR)}:/trace-tools:ro",
            "-w", self.working_dir,
            "-e", f"TRACE_PYTEST_REPORT={self.working_dir}/.trace_pytest_report.json",
            "-e", f"PYTHONPATH=/trace-tools:{self.working_dir}",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
        ]
        for key in self.env_template:
            if str(key) in os.environ:
                cmd += ["-e", str(key)]
        cmd.append(self.image)
        cmd += self._build_pytest_args(junit_path, test_paths)
        return cmd

    def _image_exists(self) -> bool:
        proc = subprocess.run(["docker", "image", "inspect", self.image], capture_output=True, text=True, timeout=10)
        return proc.returncode == 0

    def _ensure_image(self) -> dict[str, Any]:
        if self.pull_policy == "never":
            if not self._image_exists():
                raise DockerExecutorUnavailable(f"docker image is not available locally: {self.image}")
            return {"pull_policy": self.pull_policy, "image_available": True, "pulled": False}
        if self.pull_policy == "if_missing" and self._image_exists():
            return {"pull_policy": self.pull_policy, "image_available": True, "pulled": False}
        proc = subprocess.run(["docker", "pull", self.image], capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            raise DockerExecutorUnavailable(_as_text(proc.stderr or proc.stdout) or f"failed to pull docker image: {self.image}")
        return {"pull_policy": self.pull_policy, "image_available": True, "pulled": True}

    def run(self, work_dir: Path, test_paths: list[str], timeout_seconds: int) -> RawPytestRun:
        work_dir = Path(work_dir).resolve()
        report_path = work_dir / ".trace_pytest_report.json"
        junit_path = work_dir / ".trace_junit.xml"
        for p in (report_path, junit_path):
            if p.exists():
                p.unlink()

        cmd = self._docker_run_cmd(work_dir, test_paths)
        image_metadata = self._ensure_image()
        start = time.monotonic()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
        except FileNotFoundError as exc:
            raise DockerExecutorUnavailable("docker CLI is not available") from exc
        except subprocess.TimeoutExpired as exc:
            dur = int((time.monotonic() - start) * 1000)
            return RawPytestRun(
                exit_code=-1,
                stdout=_as_text(exc.stdout),
                stderr=_as_text(exc.stderr),
                report=None,
                duration_ms=dur,
                timed_out=True,
                executor_metadata={
                    "executor": self.capabilities().as_dict(),
                    "command": cmd,
                    "image": self.image,
                    "image_metadata": image_metadata,
                    "workspace_mount": {"host_path": str(work_dir), "container_path": self.working_dir},
                    "artifact_paths": [str(report_path), str(junit_path)],
                },
            )

        dur = int((time.monotonic() - start) * 1000)
        report = None
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except Exception:
                report = None
        return RawPytestRun(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            report=report,
            duration_ms=dur,
            executor_metadata={
                "executor": self.capabilities().as_dict(),
                "command": cmd,
                "image": self.image,
                "image_metadata": image_metadata,
                "workspace_mount": {"host_path": str(work_dir), "container_path": self.working_dir},
                "artifact_paths": [str(report_path), str(junit_path)],
                "container_exit_code": proc.returncode,
            },
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


def docker_available() -> tuple[bool, str | None]:
    try:
        proc = subprocess.run(["docker", "version"], capture_output=True, text=True, timeout=5)
    except FileNotFoundError:
        return False, "docker CLI is not available"
    except subprocess.TimeoutExpired:
        return False, "docker availability check timed out"
    if proc.returncode != 0:
        return False, _as_text(proc.stderr or proc.stdout) or "docker daemon is not available"
    return True, None


def executor_capabilities_from_snapshot(snapshot: dict | None) -> dict[str, Any]:
    executor = executor_from_runtime_snapshot(snapshot)
    return executor.capabilities().as_dict()


def executor_from_runtime_snapshot(snapshot: dict | None) -> PytestExecutor:
    """按冻结的 runtime snapshot 构造执行器，让 pytest 命令真正来自 snapshot（V2 §10.1）。"""
    snapshot = snapshot or {}
    test_command = snapshot.get("test_command")
    interpreter, extra = _parse_test_command(test_command)
    if snapshot.get("executor") == "docker":
        return DockerPytestExecutor(
            image=str(snapshot.get("image") or ""),
            extra_pytest_args=extra,
            network_policy=str(snapshot.get("network_policy") or "default"),
            resource_limits=dict(snapshot.get("resource_limits") or {}),
            env_template=dict(snapshot.get("env_template") or {}),
            working_dir=str(snapshot.get("working_dir") or "/workspace"),
            pull_policy=str((snapshot.get("artifact_policy") or {}).get("image_pull_policy") or snapshot.get("image_pull_policy") or "if_missing"),
            cleanup_policy=dict(snapshot.get("cleanup_policy") or {}),
        )
    return LocalSubprocessExecutor(python_executable=interpreter, extra_pytest_args=extra)
