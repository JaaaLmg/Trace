import pytest
from pydantic import BaseModel

from app.agents.llm import Message, MockLLM
from app.agents.recorder import InMemoryRecorder
from app.agents.structured import _extract_json, generate_structured
from app.core.errors import TraceError
from app.schemas.records import TestRunRecord


class Foo(BaseModel):
    a: int
    b: str


def _msgs():
    return [Message(role="user", content="give foo")]


def test_structured_ok():
    llm = MockLLM(['{"a": 1, "b": "x"}'])
    res = generate_structured(llm, _msgs(), Foo)
    assert res.value.a == 1 and res.value.b == "x"
    assert res.attempts == 1
    assert res.tokens > 0


def test_structured_strips_fence():
    llm = MockLLM(['```json\n{"a": 2, "b": "y"}\n```'])
    res = generate_structured(llm, _msgs(), Foo)
    assert res.value.a == 2


def test_structured_retries_then_succeeds():
    # 第一次给非 JSON，把错误反馈回去后第二次给对
    llm = MockLLM(["not json at all", '{"a": 3, "b": "z"}'])
    res = generate_structured(llm, _msgs(), Foo)
    assert res.value.a == 3
    assert res.attempts == 2
    assert llm.calls == 2


def test_structured_raises_after_retries():
    llm = MockLLM(["nope", "still nope", "nope again"])
    with pytest.raises(TraceError):
        generate_structured(llm, _msgs(), Foo, max_retries=2)


def test_structured_attempt_logs_capture_retry():
    # 重试成功：两次调用都要落 attempt_logs（首次失败带 error，二次成功 error=None）
    bad, good = "not json at all", '{"a": 3, "b": "z"}'
    res = generate_structured(MockLLM([bad, good]), _msgs(), Foo)
    assert res.attempts == 2 and len(res.attempt_logs) == 2
    assert res.attempt_logs[0]["error"] and res.attempt_logs[0]["raw_text"] == bad
    assert res.attempt_logs[1]["error"] is None
    # 第二次的 messages 必须带上重试反馈，否则没法复现那次真实输入
    assert any("只返回合法 JSON" in m["content"] for m in res.attempt_logs[1]["messages"])


def test_structured_failure_carries_attempt_logs():
    # 彻底失败：异常 details 里要带齐每次调用的 attempt_logs + 消耗的 token，供上层落 error trace
    llm = MockLLM(["nope", "still nope", "nope again"])
    with pytest.raises(TraceError) as ei:
        generate_structured(llm, _msgs(), Foo, max_retries=2)
    details = ei.value.details or {}
    logs = details.get("attempt_logs") or []
    assert len(logs) == 3 and all(x["error"] for x in logs)
    assert details.get("tokens", 0) > 0  # 失败也烧了 token，不能丢


def test_extract_json_plain():
    assert _extract_json('prefix {"a":1} suffix') == '{"a":1}'


def test_recorder_upsert():
    rec = InMemoryRecorder()
    run = TestRunRecord(strategy_version_id="sv1")
    rec.save_run(run)
    run.status = "running"
    rec.save_run(run)  # 同 id upsert，不新增
    assert len(rec.runs) == 1
    assert rec.runs[run.id].status == "running"
