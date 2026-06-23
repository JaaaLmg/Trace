from __future__ import annotations

from app.agents.prompts import build_generate_messages
from app.schemas.agent import PlanItemDraft
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


def test_generate_prompt_isolates_focused_plan_item_target():
    messages = build_generate_messages(
        _strategy(),
        AnalyzeProjectOutput(),
        ["apply_discount", "loyalty_points"],
        "生成 pricing 测试",
        PlanItemDraft(
            index=0,
            target_type="function",
            target_ref="apply_discount",
            goal="只验证 apply_discount 的会员折扣边界",
            planned_assertions=["会员阈值折扣"],
        ),
        source_context="def apply_discount(total, member):\n    return total\n",
    )

    body = messages[-1].content
    assert "本次聚焦任务" in body
    assert "target=function:apply_discount" in body
    assert "只能为该 target 生成 pytest 函数和 cases" in body
    assert "不能把依赖函数写成独立 case" in body
