from __future__ import annotations

import pytest

from app.core.errors import TraceError
from app.schemas.tools import LspDefinitionInput
from app.tools import default_registry, lsp_definition
from app.tools.base import ToolContext


def _ctx(tmp_path):
    write_dir = tmp_path / "tests" / "generated"
    write_dir.mkdir(parents=True, exist_ok=True)
    return ToolContext(root=tmp_path, test_write_dir=write_dir)


def test_lsp_definition_returns_structured_function_evidence(tmp_path):
    (tmp_path / "shop").mkdir()
    (tmp_path / "shop" / "pricing.py").write_text(
        "def helper(total):\n"
        "    return round(total, 2)\n"
        "\n"
        "\n"
        "def target_fn(total):\n"
        "    return helper(total)\n",
        encoding="utf-8",
    )

    out = lsp_definition(_ctx(tmp_path), LspDefinitionInput(query="helper", path="shop"))

    assert out.status == "resolved"
    assert out.engine == "python_ast_fallback"
    assert out.warnings
    match = out.definitions[0]
    assert match.retrieval_source == "lsp"
    assert match.engine == "python_ast_fallback"
    assert match.source_path == "shop/pricing.py"
    assert match.symbol == "helper"
    assert match.line_range == {"start": 1, "end": 2}
    assert "def helper" in match.matched_text
    assert match.trace_id.startswith("lsp-")
    assert len(match.content_hash) == 64
    assert 0 < match.confidence <= 1


def test_lsp_definition_returns_class_method_symbol(tmp_path):
    (tmp_path / "shop").mkdir()
    (tmp_path / "shop" / "pricing.py").write_text(
        "class PriceCalculator:\n"
        "    def normalize(self, total):\n"
        "        return round(total, 2)\n",
        encoding="utf-8",
    )

    out = lsp_definition(_ctx(tmp_path), LspDefinitionInput(query="PriceCalculator.normalize", path="shop"))

    assert out.status == "resolved"
    assert out.definitions[0].symbol == "PriceCalculator.normalize"


def test_lsp_definition_reports_missing_structurally(tmp_path):
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    out = lsp_definition(_ctx(tmp_path), LspDefinitionInput(query="subtract", path="."))

    assert out.status == "missing"
    assert out.definitions == []
    assert out.engine == "python_ast_fallback"


def test_lsp_definition_rejects_path_escape(tmp_path):
    (tmp_path.parent / "secret.py").write_text("def secret():\n    return 1\n", encoding="utf-8")

    with pytest.raises(TraceError):
        lsp_definition(_ctx(tmp_path), LspDefinitionInput(query="secret", path="../secret.py"))


def test_default_registry_exposes_lsp_definition_tool(tmp_path):
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    registry = default_registry()

    assert "lsp_definition" in registry.names()
    out = registry.call(_ctx(tmp_path), "lsp_definition", {"query": "add", "path": "."})

    assert out.definitions[0].source_path == "calc.py"
