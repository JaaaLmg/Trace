# 结构化输出 + 重试：让 LLM 输出过 Pydantic 校验，失败把错误反馈回去再试。
# 这是「所有模型输出都要结构化、可校验」原则的落点（需求分析 §9.4）。
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.agents.llm import LLMClient, Message
from app.core.errors import ErrorCode, TraceError

T = TypeVar("T", bound=BaseModel)


@dataclass
class StructuredResult:
    value: BaseModel
    tokens: int  # 这次结构化输出（含重试）累计消耗
    attempts: int
    attempt_logs: list  # 每次 LLM 调用的 {attempt, messages, raw_text, error}，供 trace 完整复现


def _extract_json(text: str) -> str:
    # 容错：剥 ```json ... ``` 围栏；否则取第一个 { 到最后一个 }
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text.strip()


def _log_attempt(logs: list, attempt: int, msgs: list[Message], raw_text: str, error) -> None:
    logs.append(
        {
            "attempt": attempt,
            "messages": [{"role": m.role, "content": m.content} for m in msgs],
            "raw_text": raw_text,
            "error": error,
        }
    )


def generate_structured(
    llm: LLMClient, messages: list[Message], schema: Type[T], max_retries: int = 2
) -> StructuredResult:
    total_tokens = 0
    msgs = list(messages)
    last_err = None
    attempt_logs: list = []
    for attempt in range(1, max_retries + 2):
        resp = llm.complete(msgs)
        total_tokens += resp.tokens
        raw = _extract_json(resp.text)
        err = None
        value = None
        try:
            data = json.loads(raw)
            value = schema.model_validate(data)
        except json.JSONDecodeError as e:
            err = f"JSON 解析失败：{e}"
        except ValidationError as e:
            err = f"schema 校验失败：{e}"
        # 每次调用都记：完整输入 messages + 原始输出 + 错误（成功则 error=None），重试也不丢
        _log_attempt(attempt_logs, attempt, msgs, resp.text, err)
        if err is None:
            return StructuredResult(value=value, tokens=total_tokens, attempts=attempt, attempt_logs=attempt_logs)
        last_err = err
        if attempt <= max_retries:
            # 把错误反馈回去，让模型自我修正
            msgs = msgs + [
                Message(
                    role="user",
                    content=f"上次输出无法解析为要求的结构：{last_err}。只返回合法 JSON，不要解释、不要 markdown 围栏。",
                )
            ]
    # 失败：把 attempt_logs + 已消耗 token 挂到异常 details，上层 think() 据此累计 token 并落 error trace
    raise TraceError(
        ErrorCode.INVALID_MODEL_OUTPUT,
        last_err or "结构化输出失败",
        details={"attempt_logs": attempt_logs, "tokens": total_tokens},
    )
