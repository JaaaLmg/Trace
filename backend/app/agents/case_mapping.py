# 生成测试文件 → generated_test_cases 的 AST 登记 + pytest nodeid 对齐辅助。
# 对齐 系统设计.md §pytest_case_results 的映射策略：参数化 test_x[a]/[b] 归并到父级 test_x。
from __future__ import annotations

import ast


def parse_generated_cases(content: str) -> list[dict]:
    """抽生成文件里 test_* 函数/方法的名字与起止行。语法错误时返回空（收集阶段会暴露）。"""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    out: list[dict] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            out.append(
                {
                    "test_name": node.name,
                    "start_line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno) or node.lineno,
                }
            )
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for m in node.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name.startswith("test"):
                    out.append(
                        {
                            "test_name": m.name,
                            "class": node.name,
                            "start_line": m.lineno,
                            "end_line": getattr(m, "end_lineno", m.lineno) or m.lineno,
                        }
                    )
    return out


def base_nodeid(nodeid: str) -> str:
    # 去掉参数化后缀：tests/x.py::test_x[a] -> tests/x.py::test_x
    return nodeid.split("[", 1)[0]


def nodeid_for_case(path: str, parsed_case: dict) -> str:
    parts = [path]
    if parsed_case.get("class"):
        parts.append(parsed_case["class"])
    parts.append(parsed_case["test_name"])
    return "::".join(parts)


def test_name_of(nodeid: str) -> str:
    return base_nodeid(nodeid).split("::")[-1]
