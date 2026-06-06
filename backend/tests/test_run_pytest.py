import pytest

from app.core.errors import TraceError
from app.schemas.tools import RunPytestInput
from app.tools import run_pytest
from app.tools.base import ToolContext

# 三种结局：通过 / 断言失败 / call 阶段 import 失败
SAMPLE = """
def test_pass():
    assert 1 == 1


def test_fail():
    assert 1 == 2


def test_import_error():
    import definitely_missing_module_xyz  # noqa
"""

# 模块级 import 失败 = 收集阶段崩，0 个用例被收集
COLLECT_FAIL = """
import definitely_missing_module_xyz  # noqa


def test_never():
    assert True
"""


def _ctx(tmp_path):
    tdir = tmp_path / "tests" / "generated"
    tdir.mkdir(parents=True)
    return ToolContext(root=tmp_path, test_write_dir=tdir)


def test_run_pytest_parses_and_classifies(tmp_path):
    ctx = _ctx(tmp_path)
    (ctx.test_write_dir / "test_sample.py").write_text(SAMPLE, encoding="utf-8")

    out = run_pytest(ctx, RunPytestInput(test_paths=["tests/generated/test_sample.py"]))

    assert out.error is None
    assert out.passed == 1
    assert out.failed == 2
    assert out.collected == 3
    assert out.exit_code != 0

    by = {c.nodeid.split("::")[-1]: c for c in out.case_results}
    assert by["test_pass"].status == "passed"
    assert by["test_fail"].status == "failed"
    assert by["test_fail"].failure_type == "assertion"
    # P2：原始判据不丢，能审计/重算
    assert by["test_fail"].exc_type == "AssertionError"
    assert by["test_fail"].when_failed == "call"
    assert by["test_import_error"].failure_type == "import"
    assert by["test_import_error"].exc_type in ("ModuleNotFoundError", "ImportError")


def test_run_pytest_collection_error_isolated(tmp_path):
    ctx = _ctx(tmp_path)
    (ctx.test_write_dir / "test_broken.py").write_text(COLLECT_FAIL, encoding="utf-8")

    out = run_pytest(ctx, RunPytestInput(test_paths=["tests/generated/test_broken.py"]))

    # P2：收集失败绝不污染 collected / passed / failed / case_results
    assert out.collected == 0
    assert out.passed == 0 and out.failed == 0
    assert out.case_results == []
    assert len(out.collection_errors) == 1
    assert out.collection_errors[0].failure_type == "import"


def test_run_pytest_empty_is_not_error(tmp_path):
    ctx = _ctx(tmp_path)
    (ctx.test_write_dir / "test_empty.py").write_text("# 没有任何用例\n", encoding="utf-8")

    out = run_pytest(ctx, RunPytestInput(test_paths=["tests/generated/test_empty.py"]))
    assert out.collected == 0
    assert out.error is None


def test_run_pytest_rejects_path_escape(tmp_path):
    # P1：越界路径、以及 test_write_dir 之外的路径，都要被白名单挡掉
    ctx = _ctx(tmp_path)
    with pytest.raises(TraceError):
        run_pytest(ctx, RunPytestInput(test_paths=["../evil.py"]))
    with pytest.raises(TraceError):
        run_pytest(ctx, RunPytestInput(test_paths=["tests/other/test_x.py"]))
