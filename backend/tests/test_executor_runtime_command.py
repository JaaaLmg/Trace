from __future__ import annotations

from pathlib import Path

from app.tools.executor import (
    LocalSubprocessExecutor,
    _parse_test_command,
    executor_from_runtime_snapshot,
)


def test_default_command_keeps_mandatory_flags(tmp_path: Path):
    cmd = LocalSubprocessExecutor()._build_cmd(tmp_path, tmp_path / "j.xml", ["tests/generated"])
    # 结构性参数始终在：trace 插件、关缓存、钉 rootdir、屏蔽 addopts、junit。
    assert "_trace_pytest_plugin" in cmd
    assert "no:cacheprovider" in cmd
    assert "--rootdir" in cmd
    assert "addopts=" in cmd
    assert cmd[0].endswith("python") or cmd[0].endswith("python.exe") or "python" in cmd[0].lower()
    assert "-q" in cmd and "--no-header" in cmd


def test_test_command_drives_passthrough_args(tmp_path: Path):
    snap = {"test_command": "python -m pytest tests -q -k pricing --maxfail=2"}
    executor = executor_from_runtime_snapshot(snap)
    cmd = executor._build_cmd(tmp_path, tmp_path / "j.xml", ["tests/generated"])
    # 来自 snapshot 的选择类参数被透传。
    assert "-k" in cmd and "pricing" in cmd
    assert "--maxfail=2" in cmd
    # 仍然带强制注入的结构性参数。
    assert "_trace_pytest_plugin" in cmd
    # -q 不重复（snapshot 已带）。
    assert cmd.count("-q") == 1


def test_explicit_interpreter_path_is_honored():
    interp, extra = _parse_test_command("/opt/venv/bin/python -m pytest -q -k foo")
    assert interp == "/opt/venv/bin/python"
    assert extra == ["-q", "-k", "foo"]


def test_quoted_interpreter_path_with_spaces_is_honored():
    interp, extra = _parse_test_command('"C:\\Program Files\\Python311\\python.exe" -m pytest -q -k foo')
    assert interp == "C:\\Program Files\\Python311\\python.exe"
    assert extra == ["-q", "-k", "foo"]


def test_bare_python_falls_back_to_sys_executable():
    import sys

    interp, _ = _parse_test_command("python -m pytest -q")
    assert interp is None
    assert executor_from_runtime_snapshot({"test_command": "python -m pytest -q"}).python_executable == sys.executable


def test_structural_flags_in_command_are_not_passed_through():
    # --rootdir / -p / -o 这些结构性参数不能从 test_command 透传，避免和执行器自注入打架。
    _, extra = _parse_test_command("python -m pytest tests --rootdir /x -p something -o addopts=foo")
    assert extra == []
