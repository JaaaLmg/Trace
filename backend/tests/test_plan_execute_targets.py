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
