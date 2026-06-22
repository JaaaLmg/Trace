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
