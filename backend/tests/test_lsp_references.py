from __future__ import annotations

import pytest

from app.core.errors import TraceError
from app.schemas.tools import LspReferenceMatch, LspReferencesInput
from app.tools import default_registry, lsp_references
import app.tools.lsp as lsp_tools
from app.tools.base import ToolContext


def _ctx(tmp_path):
    write_dir = tmp_path / "tests" / "generated"
    write_dir.mkdir(parents=True, exist_ok=True)
    return ToolContext(root=tmp_path, test_write_dir=write_dir)


def test_lsp_references_returns_structured_call_evidence(tmp_path):
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

    out = lsp_references(_ctx(tmp_path), LspReferencesInput(query="helper", path="shop"))

    assert out.status == "resolved"
    assert out.engine == "python_ast_fallback"
    assert out.warnings
    assert len(out.references) == 1
    match = out.references[0]
    assert match.retrieval_source == "lsp"
    assert match.engine == "python_ast_fallback"
    assert match.source_path == "shop/pricing.py"
    assert match.symbol == "helper"
    assert match.line_range == {"start": 6, "end": 6}
    assert "helper(total)" in match.matched_text
    assert match.trace_id.startswith("lsp-ref-")
    assert len(match.content_hash) == 64
    assert 0 < match.confidence <= 1


def test_lsp_references_returns_attribute_call_evidence(tmp_path):
    (tmp_path / "shop").mkdir()
    (tmp_path / "shop" / "pricing.py").write_text(
        "class PriceCalculator:\n"
        "    def normalize(self, total):\n"
        "        return round(total, 2)\n"
        "\n"
        "\n"
        "def make_price(calc, total):\n"
        "    return calc.normalize(total)\n",
        encoding="utf-8",
    )

    out = lsp_references(_ctx(tmp_path), LspReferencesInput(query="PriceCalculator.normalize", path="shop"))

    assert out.status == "resolved"
    assert len(out.references) == 1
    assert out.references[0].symbol == "normalize"
    assert out.references[0].line_range == {"start": 7, "end": 7}
    assert "calc.normalize(total)" in out.references[0].matched_text


def test_lsp_references_uses_pyright_when_location_is_available(tmp_path, monkeypatch):
    (tmp_path / "shop").mkdir()
    (tmp_path / "shop" / "pricing.py").write_text(
        "def helper(total):\n"
        "    return total\n"
        "\n"
        "\n"
        "def target_fn(total):\n"
        "    return helper(total)\n",
        encoding="utf-8",
    )

    def fake_references(ctx, command, inp):
        return [
            LspReferenceMatch(
                source_path="shop/pricing.py",
                line_range={"start": 6, "end": 6},
                matched_text="    return helper(total)",
                symbol="helper",
                content_hash="a" * 64,
                trace_id="lsp-ref-fake",
                confidence=0.86,
                engine="pyright_lsp",
            )
        ]

    monkeypatch.setattr(lsp_tools.shutil, "which", lambda name: "pyright-langserver" if name == "pyright-langserver" else None)
    monkeypatch.setattr(lsp_tools, "_references_with_pyright_lsp", fake_references)

    out = lsp_references(
        _ctx(tmp_path),
        LspReferencesInput(query="helper", path="shop", from_path="shop/pricing.py", line=6, column=12),
    )

    assert out.status == "resolved"
    assert out.engine == "pyright_lsp"
    assert out.references[0].engine == "pyright_lsp"


def test_lsp_references_reports_missing_structurally(tmp_path):
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    out = lsp_references(_ctx(tmp_path), LspReferencesInput(query="subtract", path="."))

    assert out.status == "missing"
    assert out.references == []
    assert out.engine == "python_ast_fallback"


def test_lsp_references_rejects_path_escape(tmp_path):
    (tmp_path.parent / "secret.py").write_text("def secret():\n    return 1\n", encoding="utf-8")

    with pytest.raises(TraceError):
        lsp_references(_ctx(tmp_path), LspReferencesInput(query="secret", path="../secret.py"))


def test_default_registry_exposes_lsp_references_tool(tmp_path):
    (tmp_path / "calc.py").write_text(
        "def add(a, b):\n"
        "    return a + b\n"
        "\n"
        "\n"
        "def use_add():\n"
        "    return add(1, 2)\n",
        encoding="utf-8",
    )
    registry = default_registry()

    assert "lsp_references" in registry.names()
    out = registry.call(_ctx(tmp_path), "lsp_references", {"query": "add", "path": "."})

    assert out.references[0].source_path == "calc.py"
