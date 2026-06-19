from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess

from eval.harness.replay import replay as replay_frozen_tests
from app.tools.executor import (
    DockerPytestExecutor,
    DockerExecutorUnavailable,
    LocalSubprocessExecutor,
    executor_capabilities_from_snapshot,
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


def test_local_subprocess_capabilities_do_not_claim_sandbox():
    caps = LocalSubprocessExecutor().capabilities().as_dict()
    assert caps["executor_kind"] == "local_subprocess"
    assert caps["isolation_level"] == "process"
    assert caps["network_enforced"] is False
    assert caps["resource_limits_enforced"] is False
    assert "not a security sandbox" in " ".join(caps["policy_notes"])


def test_executor_factory_requires_docker_image():
    try:
        executor_from_runtime_snapshot({"executor": "docker", "test_command": "python -m pytest -q"})
    except DockerExecutorUnavailable as exc:
        assert "requires an image" in str(exc)
    else:
        raise AssertionError("docker executor without image should fail")


def test_executor_capabilities_from_docker_snapshot():
    caps = executor_capabilities_from_snapshot({
        "executor": "docker",
        "image": "python:3.12-slim",
        "test_command": "python -m pytest -q",
    })
    assert caps["executor_kind"] == "docker"
    assert caps["network_enforced"] is True


def test_docker_executor_pull_policy_never_requires_local_image(monkeypatch):
    calls: list[list[str]] = []

    class Proc:
        returncode = 1
        stdout = ""
        stderr = "missing"

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return Proc()

    monkeypatch.setattr("app.tools.executor.subprocess.run", fake_run)
    executor = DockerPytestExecutor(image="missing:test", pull_policy="never")
    try:
        executor._ensure_image()
    except DockerExecutorUnavailable as exc:
        assert "not available locally" in str(exc)
    else:
        raise AssertionError("pull_policy=never should fail when image is missing")
    assert calls == [["docker", "image", "inspect", "missing:test"]]


def test_docker_executor_runs_pytest_with_local_docker(tmp_path: Path):
    if shutil.which("docker") is None:
        import pytest

        pytest.skip("docker CLI is not available")
    if os.environ.get("TRACE_SKIP_DOCKER_TESTS") == "1":
        import pytest

        pytest.skip("TRACE_SKIP_DOCKER_TESTS=1")

    work = tmp_path / "project"
    tests_dir = work / "tests" / "generated"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_sample.py").write_text("def test_sample():\n    assert 1 + 1 == 2\n", encoding="utf-8")

    image = os.environ.get("TRACE_DOCKER_TEST_IMAGE", "trace-pytest:3.12")
    inspect = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True, timeout=10)
    if inspect.returncode != 0:
        import pytest

        pytest.skip(f"docker test image is not available locally: {image}")

    executor = DockerPytestExecutor(
        image=image,
        pull_policy="never",
        network_policy="disabled",
    )
    out = executor.run(work, ["tests/generated/test_sample.py"], timeout_seconds=60)

    assert out.exit_code == 0, out.stderr or out.stdout
    assert out.report is not None
    assert out.report["collected"] == 1
    assert out.executor_metadata
    assert out.executor_metadata["executor"]["executor_kind"] == "docker"
    assert out.executor_metadata["image_metadata"]["image_available"] is True


def test_docker_executor_replays_frozen_tests_clean_and_variant(tmp_path: Path):
    if shutil.which("docker") is None:
        import pytest

        pytest.skip("docker CLI is not available")
    if os.environ.get("TRACE_SKIP_DOCKER_TESTS") == "1":
        import pytest

        pytest.skip("TRACE_SKIP_DOCKER_TESTS=1")

    image = os.environ.get("TRACE_DOCKER_TEST_IMAGE", "trace-pytest:3.12")
    inspect = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True, timeout=10)
    if inspect.returncode != 0:
        import pytest

        pytest.skip(f"docker test image is not available locally: {image}")

    files = {
        "tests/generated/test_app.py": (
            "from app import price\n\n"
            "def test_price():\n"
            "    assert price() == 3\n"
        )
    }
    runtime_snapshot = {
        "executor": "docker",
        "image": image,
        "test_command": "python -m pytest tests -q",
        "network_policy": "disabled",
        "artifact_policy": {"image_pull_policy": "never"},
    }
    clean = tmp_path / "clean"
    variant = tmp_path / "variant"
    clean.mkdir()
    variant.mkdir()
    (clean / "app.py").write_text("def price():\n    return 3\n", encoding="utf-8")
    (variant / "app.py").write_text("def price():\n    return 4\n", encoding="utf-8")

    clean_out = replay_frozen_tests(clean, files, timeout_seconds=60, runtime_snapshot=runtime_snapshot)
    variant_out = replay_frozen_tests(variant, files, timeout_seconds=60, runtime_snapshot=runtime_snapshot)

    assert clean_out.error is None, clean_out.stderr or clean_out.stdout
    assert clean_out.passed == 1
    assert clean_out.metadata["executor"]["executor"]["executor_kind"] == "docker"
    assert variant_out.error is None, variant_out.stderr or variant_out.stdout
    assert variant_out.failed == 1
    assert variant_out.metadata["executor"]["executor"]["executor_kind"] == "docker"
