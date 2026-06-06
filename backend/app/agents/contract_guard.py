# Reflection 契约的静态闸门：别让被审的人自己打分。
# 不信任模型自报的 lowered_assertion_strength，直接比对首轮/修复版 AST，
# 抓 pytest.skip/xfail、空洞断言、宽泛 except 吞异常、断言/测试数缩水。
from __future__ import annotations

import ast

_SKIP_NAMES = {"skip", "skipif", "xfail"}
_BROAD_EXC = {"Exception", "BaseException"}


def check_reflection_contract(old_content: str, new_content: str) -> list[str]:
    """静态比对首轮/修复版，返回违规原因列表（空 = 通过）。修复版解析失败也算违规。"""
    violations: list[str] = []
    try:
        new_tree = ast.parse(new_content or "")
    except SyntaxError as e:
        return [f"修复版无法解析为 Python：{e}"]
    try:
        old_tree = ast.parse(old_content or "")
    except SyntaxError:
        old_tree = None  # 首轮本身语法错，只能单看修复版

    if _has_skip_or_xfail(new_tree):
        violations.append("引入 pytest.skip/xfail 跳过测试")
    if _has_trivial_assert(new_tree):
        violations.append("出现空洞断言（assert True / assert 1 / ... or True 之类）")
    if _has_broad_except(new_tree):
        violations.append("用宽泛 except 吞掉失败（bare except / except Exception）")

    # 绝对下限：不管首轮能否解析，修复版必须有测试函数 + 至少一个断言式检查。
    # 堵「首轮 collection error → old_tree=None → 缩水检查被跳过 → 改成空测试骗绿」的洞。
    if _count_tests(new_tree) == 0:
        violations.append("修复版没有任何测试函数")
    if _count_checks(new_tree) == 0:
        violations.append("修复版没有任何断言/pytest.raises（疑似空测试）")

    # 相对首轮不缩水；首轮语法错（collection error）无法 AST 比对，靠上面的绝对下限兜底
    if old_tree is not None:
        if _count_asserts(new_tree) < _count_asserts(old_tree):
            violations.append("断言数量较首轮减少")
        if _count_tests(new_tree) < _count_tests(old_tree):
            violations.append("测试函数数量较首轮减少")
    return violations


def _attr_chain(node) -> str:
    # a.b.c -> "a.b.c"；不是纯属性/名字链返回 ""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _last(node) -> str:
    return _attr_chain(node).rsplit(".", 1)[-1]


def _has_skip_or_xfail(tree) -> bool:
    for n in ast.walk(tree):
        # 调用：pytest.skip(...) / skip(...) / pytest.xfail(...)
        if isinstance(n, ast.Call) and _last(n.func) in _SKIP_NAMES:
            return True
        # 装饰器：@pytest.mark.skip / skipif / xfail（带不带参数都算）
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in n.decorator_list:
                target = dec.func if isinstance(dec, ast.Call) else dec
                if _last(target) in _SKIP_NAMES:
                    return True
    return False


def _is_truthy_const(node) -> bool:
    return isinstance(node, ast.Constant) and bool(node.value)


def _has_trivial_assert(tree) -> bool:
    for n in ast.walk(tree):
        if not isinstance(n, ast.Assert):
            continue
        t = n.test
        if _is_truthy_const(t):  # assert True / assert 1 / assert "x"
            return True
        # assert X or True / assert X or 1：短路成恒真
        if isinstance(t, ast.BoolOp) and isinstance(t.op, ast.Or):
            if any(_is_truthy_const(v) for v in t.values):
                return True
    return False


def _has_broad_except(tree) -> bool:
    for n in ast.walk(tree):
        if isinstance(n, ast.ExceptHandler):
            if n.type is None:  # bare except:
                return True
            if _last(n.type) in _BROAD_EXC:  # except Exception/BaseException
                return True
    return False


def _count_asserts(tree) -> int:
    return sum(isinstance(n, ast.Assert) for n in ast.walk(tree))


def _count_checks(tree) -> int:
    # 断言式检查：assert 语句 + pytest.raises/warns + assertXxx(...) 调用
    n = _count_asserts(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _last(node.func)
            if name in ("raises", "warns") or name.startswith("assert"):
                n += 1
    return n


def _count_tests(tree) -> int:
    # 与 pytest 默认收集规则一致：test 开头的函数/方法
    return sum(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test")
        for n in ast.walk(tree)
    )
