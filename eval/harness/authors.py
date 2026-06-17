# demo 测试作者：驱动 MockLLM 为 shop 项目生成 pytest 测试。
#
# 这是评测的「被试模型」替身：不接真模型也能跑通 harness。它刻意建模三种策略的典型行为，
# 以覆盖 harness 的每条路径（捕获 / 漏判 / 假阳性 / 反思修复）：
#   - 单发（Direct/ReAct 的首轮，无 focus）：覆盖 5 个定价函数 + 一个「状态码写反」的路由测试；
#   - 逐目标（Plan-and-Execute，带 focus）：每个目标单独生成，路由测试写对；
#   - 反思（ReAct 失败后）：把写反的路由状态码断言修正回来。
# 换成真 LLM 时，这些行为由模型涌现，harness 指标计算不变。
from __future__ import annotations

import json

# 函数名 -> (测试函数名, 断言)。断言值刻意等于 ground truth 的 clean 行为：干净通过、对应变体失败。
FUNC_TESTS = {
    "apply_discount": ("test_apply_discount", "assert apply_discount(100, True) == 90.0"),
    "shipping_fee": ("test_shipping_fee", "assert shipping_fee(5) == 10"),
    "clamp_discount_rate": ("test_clamp_discount_rate", "assert clamp_discount_rate(1.5) == 1.0"),
    "is_free_shipping": ("test_is_free_shipping", "assert is_free_shipping(250) is True"),
    "loyalty_points": ("test_loyalty_points", "assert loyalty_points(3) == 100"),
}
_ROUTE_TEST_NAME = "test_get_price_missing_item"


def _gen_payload(content: str, cases: list[dict]) -> str:
    return json.dumps({"test_file_content": content, "cases": cases, "coverage_notes": "demo author"}, ensure_ascii=False)


def _route_block(status: int) -> str:
    return (
        f"def {_ROUTE_TEST_NAME}():\n"
        "    response = TestClient(app).get('/price/unknown')\n"
        f"    assert response.status_code == {status}\n"
        "    assert response.json()['detail'] == 'item not found'\n"
    )


def _all_in_one(route_status: int) -> str:
    # 单发：一个文件覆盖全部函数 + 路由。route_status=200 是首轮「写反」的状态码。
    lines = [
        "from shop.pricing import apply_discount, shipping_fee, clamp_discount_rate, is_free_shipping, loyalty_points",
        "from fastapi.testclient import TestClient",
        "from shop.api import app",
        "",
    ]
    for _, (tn, assertion) in FUNC_TESTS.items():
        lines.append(f"def {tn}():\n    {assertion}\n")
    lines.append(_route_block(route_status))
    return "\n".join(lines)


def _all_in_one_cases() -> list[dict]:
    cases = [
        {"test_name": tn, "target_function": fn, "assertion_summary": a}
        for fn, (tn, a) in FUNC_TESTS.items()
    ]
    cases.append({"test_name": _ROUTE_TEST_NAME, "target_route": "/price/{item}", "assertion_summary": "未找到商品应为 404"})
    return cases


def _focus_target(blob: str):
    # plan/generate 的 focus 行形如 target=function:apply_discount / target=route:get_price
    marker = "target="
    idx = blob.find(marker)
    if idx == -1:
        return None
    seg = blob[idx + len(marker):]
    seg = seg.split("）")[0].split(")")[0].strip()  # 容中英文右括号
    if ":" not in seg:
        return None
    kind, _, name = seg.partition(":")
    return kind.strip(), name.strip()


def _gen_for_target(target) -> str:
    kind, name = target
    if kind == "route":
        content = (
            "from fastapi.testclient import TestClient\n"
            "from shop.api import app\n\n" + _route_block(404)  # 逐目标更稳：写对 404
        )
        return _gen_payload(content, [{"test_name": _ROUTE_TEST_NAME, "target_route": name, "assertion_summary": "未找到商品应为 404"}])
    if name in FUNC_TESTS:
        tn, assertion = FUNC_TESTS[name]
        content = f"from shop.pricing import {name}\n\ndef {tn}():\n    {assertion}\n"
        return _gen_payload(content, [{"test_name": tn, "target_function": name, "assertion_summary": assertion}])
    # 兜底：未知目标给个不空洞的占位（保持 harness 健壮）
    return _gen_payload("def test_placeholder():\n    assert 1 + 1 == 2\n", [{"test_name": "test_placeholder", "assertion_summary": "占位"}])


def _plan() -> str:
    items = [
        {"index": i, "target_type": "function", "target_ref": fn, "goal": f"测试 {fn}", "planned_assertions": [FUNC_TESTS[fn][1]]}
        for i, fn in enumerate(FUNC_TESTS)
    ]
    items.append({"index": len(FUNC_TESTS), "target_type": "route", "target_ref": "get_price", "goal": "测试 get_price 路由", "planned_assertions": ["未找到商品 -> 404"]})
    return json.dumps({"items": items}, ensure_ascii=False)


def _reflect() -> str:
    # 把首轮写反的路由状态码断言修正回 404（合法修复：不削弱、不跳过、断言数不变）
    content = _all_in_one(404)
    return json.dumps(
        {
            "fixed_content": content,
            "fix_reason": "路由测试状态码断言写反，未找到商品应返回 404",
            "changed_points": ["路由断言 200 -> 404"],
            "lowered_assertion_strength": False,
            "suspected_code_bug": False,
        },
        ensure_ascii=False,
    )


def demo_author(messages) -> str:
    blob = "\n".join(m.content for m in messages)
    if "TASK: PLAN" in blob:
        return _plan()
    if "TASK: REFLECT" in blob:
        return _reflect()
    if "TASK: GENERATE" in blob:
        target = _focus_target(blob)
        # Direct/ReAct 的任务是整体目标（target=goal:...）→ 单发覆盖全部；
        # Plan-and-Execute 拆成 function/route 子目标 → 逐目标生成。
        if target is None or target[0] == "goal":
            return _gen_payload(_all_in_one(200), _all_in_one_cases())
        return _gen_for_target(target)
    raise AssertionError("demo_author 收到未知任务：" + blob[:120])
