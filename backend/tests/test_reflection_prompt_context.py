from __future__ import annotations

from app.agents.prompts import build_reflect_messages
from app.schemas.strategy import StrategyVersionSpec
from app.schemas.tools import AnalyzeProjectOutput, FailureDetail, RunPytestOutput


def _strategy() -> StrategyVersionSpec:
    return StrategyVersionSpec(
        id="sv-react-test",
        name="react test",
        workflow_type="react_reflection",
        allow_reflection=True,
    )


def test_reflection_prompt_includes_failure_context():
    result = RunPytestOutput(
        exit_code=1,
        collected=1,
        failed=1,
        failures=[
            FailureDetail(
                nodeid="tests/generated/test_api.py::test_health",
                file="tests/generated/test_api.py",
                line=7,
                exc_type="AssertionError",
                message="assert 500 == 200",
                traceback="Traceback line 1\nTraceback line 2",
                failure_type="assertion",
            )
        ],
    )

    messages = build_reflect_messages(
        _strategy(),
        AnalyzeProjectOutput(),
        "def test_health():\n    assert False\n",
        result,
        relevant_source="def health():\n    return {'ok': True}",
    )

    body = messages[-1].content
    assert "失败上下文" in body
    assert "tests/generated/test_api.py:7" in body
    assert "AssertionError" in body
    assert "assert 500 == 200" in body
    assert "Traceback line 1" in body
    assert "相关源码" in body
