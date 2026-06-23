from __future__ import annotations

from app.agents.strategies.common import _model_field_names
from app.schemas.agent import PlanItemDraft
from app.schemas.tools import AnalyzeProjectOutput, FunctionInfo, ModelFieldInfo, ModelInfo, RouteInfo


def test_model_field_names_use_focused_route_request_model_only():
    analysis = AnalyzeProjectOutput(
        routes=[RouteInfo(method="POST", path="/prices", handler="create_price", file="api.py")],
        functions=[FunctionInfo(name="create_price", signature="create_price(req: PriceRequest)", file="api.py")],
        models=[
            ModelInfo(
                name="PriceRequest",
                file="api.py",
                fields=[ModelFieldInfo(name="sku"), ModelFieldInfo(name="quantity", type="int")],
            ),
            ModelInfo(name="AdminRequest", file="admin.py", fields=[ModelFieldInfo(name="role")]),
        ],
    )
    item = PlanItemDraft(
        index=0,
        target_type="route",
        target_ref="POST /prices",
        goal="test price creation",
        planned_assertions=[],
    )

    assert _model_field_names(analysis, item) == ["sku", "quantity"]


def test_model_field_names_do_not_use_unrelated_models_for_route_without_request_model():
    analysis = AnalyzeProjectOutput(
        routes=[RouteInfo(method="GET", path="/health", handler="health", file="api.py")],
        functions=[FunctionInfo(name="health", signature="health()", file="api.py")],
        models=[ModelInfo(name="PriceRequest", file="api.py", fields=[ModelFieldInfo(name="sku")])],
    )
    item = PlanItemDraft(
        index=0,
        target_type="route",
        target_ref="GET /health",
        goal="test health route",
        planned_assertions=[],
    )

    assert _model_field_names(analysis, item) == []


def test_model_field_names_keep_broad_fields_without_focused_item():
    analysis = AnalyzeProjectOutput(
        models=[
            ModelInfo(name="PriceRequest", file="api.py", fields=[ModelFieldInfo(name="sku")]),
            ModelInfo(name="AdminRequest", file="admin.py", fields=[ModelFieldInfo(name="role")]),
        ],
    )

    assert _model_field_names(analysis, None) == ["sku", "role"]


def test_model_field_names_include_route_query_params_from_handler_signature():
    analysis = AnalyzeProjectOutput(
        routes=[RouteInfo(method="GET", path="/prices", handler="search_prices", file="api.py")],
        functions=[FunctionInfo(name="search_prices", signature="search_prices(sku: str, limit: int = 10)", file="api.py")],
        models=[ModelInfo(name="PriceRequest", file="api.py", fields=[ModelFieldInfo(name="role")])],
    )
    item = PlanItemDraft(
        index=0,
        target_type="route",
        target_ref="GET /prices",
        goal="test price search",
        planned_assertions=[],
    )

    assert _model_field_names(analysis, item) == ["sku", "limit"]


def test_model_field_names_exclude_route_dependency_and_request_model_params():
    analysis = AnalyzeProjectOutput(
        routes=[RouteInfo(method="POST", path="/prices", handler="create_price", file="api.py")],
        functions=[
            FunctionInfo(
                name="create_price",
                signature=(
                    "create_price("
                    "req: PriceRequest, "
                    "db=Depends(get_db), "
                    "cache: Annotated[Cache, Depends(get_cache)] = None, "
                    "request: Request = None"
                    ")"
                ),
                file="api.py",
            )
        ],
        models=[ModelInfo(name="PriceRequest", file="api.py", fields=[ModelFieldInfo(name="sku")])],
    )
    item = PlanItemDraft(
        index=0,
        target_type="route",
        target_ref="POST /prices",
        goal="test price creation",
        planned_assertions=[],
    )

    assert _model_field_names(analysis, item) == ["sku"]


def test_model_field_names_include_goal_route_query_params_but_not_path_params():
    analysis = AnalyzeProjectOutput(
        routes=[RouteInfo(method="GET", path="/price/{item}", handler="get_price", file="shop/api.py")],
        functions=[FunctionInfo(name="get_price", signature="get_price(item: str, member: bool = False)", file="shop/api.py")],
    )
    item = PlanItemDraft(
        index=0,
        target_type="goal",
        target_ref="shop/api.py",
        goal="test shop pricing route",
        planned_assertions=[],
    )

    assert _model_field_names(analysis, item) == ["member"]


def test_model_field_names_include_goal_route_query_params_from_file_qualified_scope():
    analysis = AnalyzeProjectOutput(
        routes=[RouteInfo(method="GET", path="/sku/{sku}", handler="get_sku", file="inventory/api.py")],
        functions=[FunctionInfo(name="get_sku", signature="get_sku(sku: str, requested: int = 1)", file="inventory/api.py")],
    )
    item = PlanItemDraft(
        index=0,
        target_type="goal",
        target_ref="inventory/api.py::GET /sku/{sku}",
        goal="test inventory sku route",
        planned_assertions=[],
    )

    assert _model_field_names(analysis, item) == ["requested"]


def test_model_field_names_include_module_route_query_params_for_matching_scope_only():
    analysis = AnalyzeProjectOutput(
        routes=[
            RouteInfo(method="GET", path="/price/{item}", handler="get_price", file="shop/api.py"),
            RouteInfo(method="GET", path="/admin", handler="admin", file="admin/api.py"),
        ],
        functions=[
            FunctionInfo(name="get_price", signature="get_price(item: str, member: bool = False)", file="shop/api.py"),
            FunctionInfo(name="admin", signature="admin(token: str = '')", file="admin/api.py"),
        ],
    )
    item = PlanItemDraft(
        index=0,
        target_type="module",
        target_ref="shop",
        goal="test shop module",
        planned_assertions=[],
    )

    assert _model_field_names(analysis, item) == ["member"]
