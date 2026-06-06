# 数据集自测：证明 ground truth 是真的——每个 bug 在干净/变体上行为确实不同，patch 唯一命中。
# 这是评测可信的根基：惰性 bug（改了代码但行为不变）会让捕获率虚高，必须挡在数据集层。
from __future__ import annotations

import sys

import pytest

from eval.demo.bugs import BUG_TYPES, BUGS
from eval.harness import dataset


def _eval_probe(py_source: str, probe: str):
    # 在隔离命名空间里 exec 纯函数源码再 eval 探针，避免 import 缓存串味
    ns: dict = {}
    exec(compile(py_source, "<pricing>", "exec"), ns)
    return eval(probe, ns)


def test_all_four_bug_types_covered():
    assert {b.bug_type for b in BUGS} == set(BUG_TYPES)  # 翻比较符/改边界/漏校验/错状态码
    assert 5 <= len(BUGS) <= 6
    assert len({b.id for b in BUGS}) == len(BUGS)  # id 不重复


def test_patch_applies_uniquely_without_touching_clean(tmp_path):
    for i, bug in enumerate(BUGS):
        root = dataset.materialize_variant(bug, tmp_path / f"var{i}")
        text = (root / bug.file).read_text(encoding="utf-8")
        assert bug.new in text and bug.old not in text  # 变体已打 patch
        assert bug.old in (dataset.CLEAN_ROOT / bug.file).read_text(encoding="utf-8")  # 干净副本不受影响


def test_materialize_clean_rejects_dangerous_destinations():
    dangerous = [
        dataset.CLEAN_ROOT,
        dataset.CLEAN_ROOT.parent,
        dataset.CLEAN_ROOT / "_nested_work",
        dataset.CLEAN_ROOT.anchor,
    ]
    for dest in dangerous:
        with pytest.raises(ValueError):
            dataset.materialize_clean(dest)


@pytest.mark.parametrize("bug", [b for b in BUGS if b.kind == "function"], ids=lambda b: b.id)
def test_function_bug_actually_changes_behavior(bug, tmp_path):
    clean_src = (dataset.CLEAN_ROOT / bug.file).read_text(encoding="utf-8")
    root = dataset.materialize_variant(bug, tmp_path / bug.id)
    var_src = (root / bug.file).read_text(encoding="utf-8")
    assert _eval_probe(clean_src, bug.probe) == bug.clean_value
    assert _eval_probe(var_src, bug.probe) == bug.buggy_value
    assert bug.clean_value != bug.buggy_value  # 非惰性


def _route_status(root, path):
    # 从指定 root 全新导入 shop.api，拿到这份代码的行为（前后清缓存，避免串味）
    def _drop_shop():
        for name in [n for n in sys.modules if n == "shop" or n.startswith("shop.")]:
            del sys.modules[name]

    _drop_shop()
    sys.path.insert(0, str(root))
    try:
        import shop.api as api
        from fastapi.testclient import TestClient

        return TestClient(api.app).get(path).status_code
    finally:
        if str(root) in sys.path:
            sys.path.remove(str(root))
        _drop_shop()


@pytest.mark.parametrize("bug", [b for b in BUGS if b.kind == "route"], ids=lambda b: b.id)
def test_route_bug_actually_changes_behavior(bug, tmp_path):
    clean_root = dataset.materialize_clean(tmp_path / "clean")
    var_root = dataset.materialize_variant(bug, tmp_path / bug.id)
    assert _route_status(clean_root, bug.probe) == bug.clean_value
    assert _route_status(var_root, bug.probe) == bug.buggy_value
