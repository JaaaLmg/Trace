import pytest

from app.core.errors import TraceError
from app.schemas.tools import WriteTestFileInput
from app.tools import write_test_file
from app.tools.base import ToolContext


def _ctx(tmp_path):
    twd = tmp_path / "tests" / "generated"
    twd.mkdir(parents=True)
    return ToolContext(root=tmp_path, test_write_dir=twd)


def test_write_inside_whitelist(tmp_path):
    ctx = _ctx(tmp_path)
    out = write_test_file(
        ctx, WriteTestFileInput(path="tests/generated/test_a.py", content="x = 1\n")
    )
    assert out.path == "tests/generated/test_a.py"
    assert (tmp_path / "tests/generated/test_a.py").read_text(encoding="utf-8") == "x = 1\n"
    assert out.bytes == 6
    assert len(out.content_hash) == 64  # sha256 hex


def test_write_rejects_business_source(tmp_path):
    # 禁写业务源码：app/main.py 不在 test_write_dir 白名单内
    ctx = _ctx(tmp_path)
    with pytest.raises(TraceError):
        write_test_file(ctx, WriteTestFileInput(path="app/main.py", content="evil"))


def test_write_rejects_parent_escape(tmp_path):
    ctx = _ctx(tmp_path)
    with pytest.raises(TraceError):
        write_test_file(ctx, WriteTestFileInput(path="../outside.py", content="evil"))


def test_context_rejects_write_dir_outside_root(tmp_path):
    # P3 不变量：写目录必须在 root 内，否则白名单失去意义
    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    with pytest.raises(TraceError):
        ToolContext(root=root, test_write_dir=outside)


def test_context_rejects_write_dir_equal_root(tmp_path):
    # 第 2 轮收严：等于 root 也不行，必须严格子目录，否则能写业务源码 / 空路径退化跑全仓
    with pytest.raises(TraceError):
        ToolContext(root=tmp_path, test_write_dir=tmp_path)
