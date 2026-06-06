# 静态契约闸门单测：直接喂首轮/修复版源码对，验证各类「偷偷削弱」都被抓住。
# 这些不起子进程，快；端到端的「模型撒谎」集成验证在 test_e2e_mockllm.py。
from __future__ import annotations

from app.agents.contract_guard import check_reflection_contract

# 首轮：两个有意义的断言
OLD = "def test_x():\n    assert f(2) == 5\n    assert g() is True\n"


def test_legit_fix_passes():
    # 只改期望值（5->4），断言形态不变 → 放行
    new = "def test_x():\n    assert f(2) == 4\n    assert g() is True\n"
    assert check_reflection_contract(OLD, new) == []


def test_trivial_assert_true():
    new = "def test_x():\n    assert True\n    assert g() is True\n"
    assert any("空洞断言" in v for v in check_reflection_contract(OLD, new))


def test_assert_or_true_short_circuit():
    new = "def test_x():\n    assert f(2) == 4 or True\n    assert g() is True\n"
    assert any("空洞断言" in v for v in check_reflection_contract(OLD, new))


def test_pytest_skip_call():
    new = "import pytest\ndef test_x():\n    pytest.skip('todo')\n    assert f(2) == 4\n    assert g() is True\n"
    assert any("skip" in v for v in check_reflection_contract(OLD, new))


def test_skip_marker():
    new = "import pytest\n@pytest.mark.skip\ndef test_x():\n    assert f(2) == 4\n    assert g() is True\n"
    assert any("skip" in v for v in check_reflection_contract(OLD, new))


def test_broad_except_swallow():
    new = (
        "def test_x():\n"
        "    try:\n"
        "        assert f(2) == 4\n"
        "    except Exception:\n"
        "        pass\n"
        "    assert g() is True\n"
    )
    assert any("except" in v for v in check_reflection_contract(OLD, new))


def test_assert_count_drop():
    new = "def test_x():\n    assert f(2) == 4\n"  # 删掉第二个断言
    assert any("断言数量" in v for v in check_reflection_contract(OLD, new))


def test_test_function_count_drop():
    old2 = "def test_a():\n    assert 1 == 2\n\ndef test_b():\n    assert 2 == 3\n"
    new = "def test_a():\n    assert 1 == 2\n"  # 删了一个测试函数
    assert any("测试函数数量" in v for v in check_reflection_contract(old2, new))


def test_unparsable_fix_is_violation():
    assert check_reflection_contract(OLD, "def test_x(:\n    assert 1") != []


def test_empty_test_after_unparsable_old():
    # Codex 第 2 轮的洞：首轮语法错（collection error）→ 反思改成空测试骗绿，必须拦下
    old = "def test_x(:\n    assert f() == 1\n"  # 语法错，old_tree=None
    new = "def test_x():\n    pass\n"
    v = check_reflection_contract(old, new)
    assert any("空测试" in x for x in v)


def test_pass_body_is_violation_even_with_good_old():
    new = "def test_x():\n    pass\n"  # 0 断言
    assert any("空测试" in x for x in check_reflection_contract(OLD, new))


def test_pytest_raises_only_passes_floor():
    # 只用 pytest.raises、没有 assert，仍是有意义的检查 → 放行（首轮无法解析时也不误杀）
    old = "def test_x(:\n    bad\n"
    new = "import pytest\ndef test_x():\n    with pytest.raises(ValueError):\n        f(-1)\n"
    assert check_reflection_contract(old, new) == []
