from app.agents.strategies.plan_execute import _normalize_plan_items
from app.schemas.agent import PlanItemDraft
from app.schemas.tools import AnalyzeProjectOutput, FunctionInfo, RouteInfo


def test_plan_execute_normalizes_route_handler_to_method_path():
    analysis = AnalyzeProjectOutput(
        routes=[RouteInfo(method="GET", path="/price/{item}", handler="get_price", file="shop/api.py")]
    )
    items = [
        PlanItemDraft(
            index=0,
            target_type="route",
            target_ref="get_price",
            goal="覆盖价格查询路由",
            planned_assertions=["unknown item -> 404"],
        )
    ]

    normalized = _normalize_plan_items(items, analysis)

    assert normalized[0].target_ref == "GET /price/{item}"


def test_plan_execute_normalizes_route_path_to_method_path():
    analysis = AnalyzeProjectOutput(
        routes=[RouteInfo(method="GET", path="/price/{item}", handler="get_price", file="shop/api.py")]
    )
    items = [
        PlanItemDraft(
            index=0,
            target_type="route",
            target_ref="/price/{item}",
            goal="覆盖价格查询路由",
            planned_assertions=["unknown item -> 404"],
        )
    ]

    normalized = _normalize_plan_items(items, analysis)

    assert normalized[0].target_ref == "GET /price/{item}"


def test_plan_execute_normalizes_file_qualified_route_to_method_path():
    analysis = AnalyzeProjectOutput(
        routes=[RouteInfo(method="GET", path="/price/{item}", handler="get_price", file="shop/api.py")]
    )
    items = [
        PlanItemDraft(
            index=0,
            target_type="route",
            target_ref="route:shop/api.py::GET /price/{item}",
            goal="覆盖价格查询路由",
            planned_assertions=["unknown item -> 404"],
        )
    ]

    normalized = _normalize_plan_items(items, analysis)

    assert normalized[0].target_ref == "GET /price/{item}"


def test_plan_execute_normalizes_route_with_handler_suffix_to_method_path():
    analysis = AnalyzeProjectOutput(
        routes=[RouteInfo(method="GET", path="/sku/{sku}", handler="get_sku", file="inventory/api.py")]
    )
    items = [
        PlanItemDraft(
            index=0,
            target_type="route",
            target_ref="GET /sku/{sku} -> inventory.api.get_sku",
            goal="覆盖 SKU 查询路由",
            planned_assertions=["requested boundary"],
        )
    ]

    normalized = _normalize_plan_items(items, analysis)

    assert normalized[0].target_ref == "GET /sku/{sku}"


def test_plan_execute_normalizes_qualified_function_to_name():
    analysis = AnalyzeProjectOutput(
        functions=[FunctionInfo(name="apply_discount", signature="apply_discount(price, member)", file="shop/pricing.py")]
    )
    items = [
        PlanItemDraft(
            index=0,
            target_type="function",
            target_ref="shop.pricing.apply_discount",
            goal="覆盖会员折扣",
            planned_assertions=["member gets discount"],
        )
    ]

    normalized = _normalize_plan_items(items, analysis)

    assert normalized[0].target_ref == "apply_discount"


def test_plan_execute_strips_scenario_words_from_function_target_ref():
    analysis = AnalyzeProjectOutput(
        functions=[FunctionInfo(name="repair_json", signature="repair_json(json_str, strict=False)", file="pkg/repair.py")]
    )
    items = [
        PlanItemDraft(
            index=0,
            target_type="function",
            target_ref="repair_json strict mode",
            goal="覆盖 strict mode 的异常路径",
            planned_assertions=["strict duplicate keys raise"],
        )
    ]

    normalized = _normalize_plan_items(items, analysis)

    assert normalized[0].target_ref == "repair_json"
    assert normalized[0].goal == "覆盖 strict mode 的异常路径"


def test_plan_execute_converts_file_path_mislabeled_as_function_to_file_target():
    analysis = AnalyzeProjectOutput(
        functions=[
            FunctionInfo(name="can_withdraw", signature="can_withdraw(balance, amount)", file="accounts/policy.py"),
            FunctionInfo(name="risk_tier", signature="risk_tier(score)", file="accounts/policy.py"),
        ]
    )
    items = [
        PlanItemDraft(
            index=0,
            target_type="function",
            target_ref="accounts/policy.py",
            goal="覆盖账户策略模块中金额、费率与分层规则的核心分支和边界。",
            planned_assertions=["can_withdraw 边界", "risk_tier 分层"],
        )
    ]

    normalized = _normalize_plan_items(items, analysis)

    assert normalized[0].target_type == "file"
    assert normalized[0].target_ref == "accounts/policy.py"
