# demo 测试作者：驱动 MockLLM 为 demo 项目生成 pytest 测试。
#
# 这是评测的「被试模型」替身：不接真模型也能跑通 harness。它刻意建模三种策略的典型行为，
# 以覆盖 harness 的每条路径（捕获 / 漏判 / 假阳性 / 反思修复）：
#   - 单发（Direct/ReAct 的首轮，无 focus）：覆盖当前任务函数 + 一个「状态码写反」的路由测试；
#   - 逐目标（Plan-and-Execute，带 focus）：每个目标单独生成，路由测试写对；
#   - 反思（ReAct 失败后）：把写反的路由状态码断言修正回来。
# 换成真 LLM 时，这些行为由模型涌现，harness 指标计算不变。
from __future__ import annotations

from dataclasses import dataclass
import json


@dataclass(frozen=True)
class FunctionSpec:
    module: str
    test_name: str
    assertion: str


@dataclass(frozen=True)
class RouteSpec:
    module: str
    path: str
    route_label: str
    test_name: str
    detail: str
    summary: str


GROUPS = ("shop", "inventory", "accounts")

# 函数名 -> 断言。断言值等于 ground truth 的 clean 行为：干净通过、对应变体失败。
FUNC_TESTS: dict[str, FunctionSpec] = {
    "apply_discount": FunctionSpec("shop.pricing", "test_shop_apply_discount", "assert apply_discount(100, True) == 90.0"),
    "shipping_fee": FunctionSpec("shop.pricing", "test_shop_shipping_fee", "assert shipping_fee(5) == 10"),
    "clamp_discount_rate": FunctionSpec(
        "shop.pricing",
        "test_shop_clamp_discount_rate",
        "assert clamp_discount_rate(1.5) == 1.0",
    ),
    "is_free_shipping": FunctionSpec("shop.pricing", "test_shop_is_free_shipping", "assert is_free_shipping(250) is True"),
    "loyalty_points": FunctionSpec("shop.pricing", "test_shop_loyalty_points", "assert loyalty_points(3) == 100"),
    "has_stock": FunctionSpec("inventory.stock", "test_inventory_has_stock", "assert has_stock(5, 5) is True"),
    "reorder_quantity": FunctionSpec(
        "inventory.stock",
        "test_inventory_reorder_quantity",
        "assert reorder_quantity(10, 10, 25) == 15",
    ),
    "clamp_quantity": FunctionSpec("inventory.stock", "test_inventory_clamp_quantity", "assert clamp_quantity(-3) == 0"),
    "pack_count": FunctionSpec("inventory.stock", "test_inventory_pack_count", "assert pack_count(11, 5) == 3"),
    "can_withdraw": FunctionSpec("accounts.policy", "test_accounts_can_withdraw", "assert can_withdraw(100, 100) is True"),
    "overdraft_fee": FunctionSpec(
        "accounts.policy",
        "test_accounts_overdraft_fee",
        "assert overdraft_fee(3) == 10\n    assert overdraft_fee(0) == 0",
    ),
    "clamp_interest_rate": FunctionSpec(
        "accounts.policy",
        "test_accounts_clamp_interest_rate",
        "assert clamp_interest_rate(0.5) == 0.35",
    ),
    "risk_tier": FunctionSpec("accounts.policy", "test_accounts_risk_tier", "assert risk_tier(700) == 'low'"),
}

GROUP_FUNCTIONS = {
    "shop": ["apply_discount", "shipping_fee", "clamp_discount_rate", "is_free_shipping", "loyalty_points"],
    "inventory": ["has_stock", "reorder_quantity", "clamp_quantity", "pack_count"],
    "accounts": ["can_withdraw", "overdraft_fee", "clamp_interest_rate", "risk_tier"],
}

ROUTE_TESTS: dict[str, RouteSpec] = {
    "get_price": RouteSpec(
        module="shop.api",
        path="/price/unknown",
        route_label="/price/{item}",
        test_name="test_shop_get_price_missing_item",
        detail="item not found",
        summary="未找到商品应为 404",
    ),
    "get_sku": RouteSpec(
        module="inventory.api",
        path="/sku/missing",
        route_label="/sku/{sku}",
        test_name="test_inventory_get_sku_missing_sku",
        detail="sku not found",
        summary="未找到 SKU 应为 404",
    ),
}

GROUP_ROUTES = {"shop": ["get_price"], "inventory": ["get_sku"], "accounts": []}


def _gen_payload(content: str, cases: list[dict]) -> str:
    return json.dumps({"test_file_content": content, "cases": cases, "coverage_notes": "demo author"}, ensure_ascii=False)


def _route_block(route_name: str, status: int) -> str:
    spec = ROUTE_TESTS[route_name]
    return (
        f"def {spec.test_name}():\n"
        f"    response = TestClient(app).get('{spec.path}')\n"
        f"    assert response.status_code == {status}\n"
        f"    assert response.json()['detail'] == '{spec.detail}'\n"
    )


def _all_in_one(route_status: int, groups: list[str]) -> str:
    # 单发：一个文件覆盖当前 task 的函数 + 路由。route_status=200 是首轮「写反」的状态码。
    lines: list[str] = []
    for module, functions in _module_imports(groups).items():
        lines.append(f"from {module} import {', '.join(functions)}")
    route_names = _route_names(groups)
    if route_names:
        lines.append("from fastapi.testclient import TestClient")
        for route_name in route_names:
            spec = ROUTE_TESTS[route_name]
            lines.append(f"from {spec.module} import app as {route_name}_app")
    lines.append("")
    for fn in _function_names(groups):
        spec = FUNC_TESTS[fn]
        lines.append(f"def {spec.test_name}():\n    {spec.assertion}\n")
    for route_name in route_names:
        block = _route_block(route_name, route_status)
        lines.append(block.replace("TestClient(app)", f"TestClient({route_name}_app)"))
    return "\n".join(lines)


def _all_in_one_cases(groups: list[str]) -> list[dict]:
    cases = [
        {"test_name": FUNC_TESTS[fn].test_name, "target_function": fn, "assertion_summary": FUNC_TESTS[fn].assertion}
        for fn in _function_names(groups)
    ]
    for route_name in _route_names(groups):
        spec = ROUTE_TESTS[route_name]
        cases.append({"test_name": spec.test_name, "target_route": spec.route_label, "assertion_summary": spec.summary})
    return cases


def _function_names(groups: list[str]) -> list[str]:
    return [fn for group in groups for fn in GROUP_FUNCTIONS[group]]


def _route_names(groups: list[str]) -> list[str]:
    return [route for group in groups for route in GROUP_ROUTES[group]]


def _module_imports(groups: list[str]) -> dict[str, list[str]]:
    imports: dict[str, list[str]] = {}
    for fn in _function_names(groups):
        spec = FUNC_TESTS[fn]
        imports.setdefault(spec.module, []).append(fn)
    return imports


def _scope_blob(blob: str) -> str:
    if "范围：" not in blob:
        return blob
    scoped = blob.split("范围：", 1)[1]
    for marker in ("\n\n项目分析：", "\n项目分析："):
        if marker in scoped:
            return scoped.split(marker, 1)[0]
    return scoped.split("\n\n", 1)[0]


def _groups_from_blob(blob: str) -> list[str]:
    selected = []
    routing_blob = _scope_blob(blob) if ("TASK: PLAN" in blob or "TASK: GENERATE" in blob) else blob
    lowered = routing_blob.lower()
    for group in GROUPS:
        tokens = [group, *GROUP_FUNCTIONS[group], *GROUP_ROUTES[group]]
        if any(token.lower() in lowered for token in tokens):
            selected.append(group)
    return selected or list(GROUPS)


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


def _route_name(name: str) -> str | None:
    lowered = name.strip().lower()
    for route_name, spec in ROUTE_TESTS.items():
        aliases = {
            route_name.lower(),
            spec.path.lower(),
            spec.route_label.lower(),
            f"get {spec.route_label}".lower(),
            f"get {spec.path}".lower(),
        }
        if lowered in aliases:
            return route_name
    return None


def _gen_for_target(target) -> str:
    kind, name = target
    if kind == "route":
        route_name = _route_name(name) or name
        spec = ROUTE_TESTS.get(route_name)
        if spec is None:
            return _gen_payload("def test_placeholder():\n    assert 1 + 1 == 2\n", [{"test_name": "test_placeholder", "assertion_summary": "占位"}])
        content = (
            "from fastapi.testclient import TestClient\n"
            f"from {spec.module} import app\n\n" + _route_block(route_name, 404)  # 逐目标更稳：写对 404
        )
        return _gen_payload(content, [{"test_name": spec.test_name, "target_route": name, "assertion_summary": spec.summary}])
    if name in FUNC_TESTS:
        spec = FUNC_TESTS[name]
        content = f"from {spec.module} import {name}\n\ndef {spec.test_name}():\n    {spec.assertion}\n"
        return _gen_payload(content, [{"test_name": spec.test_name, "target_function": name, "assertion_summary": spec.assertion}])
    # 兜底：未知目标给个不空洞的占位（保持 harness 健壮）
    return _gen_payload("def test_placeholder():\n    assert 1 + 1 == 2\n", [{"test_name": "test_placeholder", "assertion_summary": "占位"}])


def _plan(blob: str) -> str:
    items = []
    for fn in _function_names(_groups_from_blob(blob)):
        spec = FUNC_TESTS[fn]
        items.append(
            {
                "index": len(items),
                "target_type": "function",
                "target_ref": fn,
                "goal": f"测试 {fn}",
                "planned_assertions": [spec.assertion],
            }
        )
    for route_name in _route_names(_groups_from_blob(blob)):
        spec = ROUTE_TESTS[route_name]
        items.append(
            {
                "index": len(items),
                "target_type": "route",
                "target_ref": route_name,
                "goal": f"测试 {route_name} 路由",
                "planned_assertions": [spec.summary],
            }
        )
    return json.dumps({"items": items}, ensure_ascii=False)


def _reflect(blob: str) -> str:
    # 把首轮写反的路由状态码断言修正回 404（合法修复：不削弱、不跳过、断言数不变）
    content = _all_in_one(404, _groups_from_blob(blob))
    return json.dumps(
        {
            "fixed_content": content,
            "fix_reason": "路由测试状态码断言写反，未找到资源应返回 404",
            "changed_points": ["路由断言 200 -> 404"],
            "lowered_assertion_strength": False,
            "suspected_code_bug": False,
        },
        ensure_ascii=False,
    )


def demo_author(messages) -> str:
    blob = "\n".join(m.content for m in messages)
    if "TASK: PLAN" in blob:
        return _plan(blob)
    if "TASK: REFLECT" in blob:
        return _reflect(blob)
    if "TASK: GENERATE" in blob:
        target = _focus_target(blob)
        # Direct/ReAct 的任务是整体目标（target=goal:...）→ 单发覆盖全部；
        # Plan-and-Execute 拆成 function/route 子目标 → 逐目标生成。
        if target is None or target[0] == "goal":
            groups = _groups_from_blob(blob)
            return _gen_payload(_all_in_one(200, groups), _all_in_one_cases(groups))
        return _gen_for_target(target)
    raise AssertionError("demo_author 收到未知任务：" + blob[:120])
