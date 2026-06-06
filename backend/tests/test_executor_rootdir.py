# 回归测试：锁住 executor 的 --rootdir=work_dir 修复。
# 评测重放靠跨 run 的 nodeid 对齐；pytest 的 nodeid 相对 rootdir，若 work_dir 落在带
# pyproject.toml 的祖先下，rootdir 会被钉到祖先，nodeid 因 work_dir 目录名不同而漂移。
# 这里构造一个祖先 pyproject.toml，断言同一份测试在两个不同 work_dir 下 nodeid 一致。
from __future__ import annotations

from app.schemas.tools import RunPytestInput, WriteTestFileInput
from app.tools.base import ToolContext
from app.tools.run_pytest import run_pytest
from app.tools.write_test import write_test_file

_TEST_SRC = "def test_one():\n    assert 1 == 1\n"


def _nodeids_under(ancestor, workname):
    root = ancestor / workname
    root.mkdir(parents=True)
    ctx = ToolContext(root=root, test_write_dir=root / "tests" / "generated")
    write_test_file(ctx, WriteTestFileInput(path="tests/generated/test_x.py", content=_TEST_SRC))
    out = run_pytest(ctx, RunPytestInput(test_paths=["tests/generated/test_x.py"]))
    return [c.nodeid for c in out.case_results]


def test_nodeid_stable_under_ancestor_pyproject(tmp_path):
    ancestor = tmp_path / "proj"
    ancestor.mkdir()
    # 祖先配置：没有 --rootdir 时会把 rootdir 抢到这里，导致 nodeid 带上 work_dir 路径段
    (ancestor / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = ['tests']\n", encoding="utf-8"
    )

    clean_ids = _nodeids_under(ancestor, "clean")
    variant_ids = _nodeids_under(ancestor, "variant_a")

    # nodeid 相对各自 work_dir，与目录名无关 → 干净/变体可对齐
    assert clean_ids == ["tests/generated/test_x.py::test_one"]
    assert clean_ids == variant_ids
