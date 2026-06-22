from __future__ import annotations

from app.agents.prompts import build_generate_messages
from app.schemas.evaluation import ContextCompletenessEvidence
from app.schemas.strategy import StrategyVersionSpec
from app.schemas.tools import AnalyzeProjectOutput


def _strategy() -> StrategyVersionSpec:
    return StrategyVersionSpec(
        id="sv-direct-test",
        name="direct test",
        workflow_type="direct",
        allow_reflection=False,
    )


def test_generate_prompt_includes_context_completeness_evidence():
    context = ContextCompletenessEvidence(
        status="partial",
        context_incomplete=True,
        missing_targets=["src/pkg/parse_string.py"],
        risk_notes=["source context truncated by max_total_bytes"],
    )

    messages = build_generate_messages(
        _strategy(),
        AnalyzeProjectOutput(),
        ["src/pkg/parser.py"],
        "生成 parser 测试",
        None,
        source_context="def parse(value):\n    return value\n",
        context_completeness=context,
    )

    body = messages[-1].content
    assert "上下文完整性" in body
    assert "status: partial" in body
    assert "src/pkg/parse_string.py" in body
    assert "source context truncated by max_total_bytes" in body
    assert "不要为不可见行为写 pytest.raises" in body


def test_generate_prompt_limits_single_file_test_volume():
    messages = build_generate_messages(
        _strategy(),
        AnalyzeProjectOutput(),
        ["src/pkg/parser.py"],
        "生成 parser 测试",
        None,
        source_context="def parse(value):\n    return value\n",
    )

    body = messages[-1].content
    assert "优先 4-8 个高价值测试函数" in body
    assert "最多 12 个" in body
