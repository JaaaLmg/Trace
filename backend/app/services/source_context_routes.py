from __future__ import annotations

import ast

HTTP_ROUTE_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"}


def looks_like_route_target(value: str) -> bool:
    _method, route_path = route_target_parts(value)
    return route_path is not None


def route_target_parts(value: str) -> tuple[str | None, str | None]:
    norm = value.strip()
    if norm.startswith("route:"):
        norm = norm.removeprefix("route:").strip()
    parts = norm.split(maxsplit=1)
    if len(parts) == 2 and parts[0].upper() in HTTP_ROUTE_METHODS:
        path = parts[1].strip()
        return (parts[0].upper(), path) if path.startswith("/") else (None, None)
    return (None, norm) if norm.startswith("/") else (None, None)


def route_path_without_method(value: str) -> str:
    norm = value.strip()
    if norm.startswith("route:"):
        norm = norm.removeprefix("route:").strip()
    parts = norm.split(maxsplit=1)
    if len(parts) == 2 and parts[0].upper() in HTTP_ROUTE_METHODS:
        return parts[1].strip()
    return norm


def route_with_method(value: str) -> str:
    norm = value.strip()
    if norm.startswith("route:"):
        norm = norm.removeprefix("route:").strip()
    return norm


def route_handler_for_path(content: str, method: str | None, path: str) -> str | None:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            route = route_decorator_parts(decorator)
            if route is None:
                continue
            decorator_method, decorator_path = route
            if decorator_path == path and (method is None or decorator_method == method):
                return node.name
    return None


def route_decorator_parts(decorator: ast.AST) -> tuple[str, str] | None:
    if not isinstance(decorator, ast.Call):
        return None
    func = decorator.func
    if not isinstance(func, ast.Attribute):
        return None
    method = func.attr.upper()
    if method not in HTTP_ROUTE_METHODS:
        return None
    if not decorator.args:
        return None
    first_arg = decorator.args[0]
    if not isinstance(first_arg, ast.Constant) or not isinstance(first_arg.value, str):
        return None
    return method, first_arg.value
