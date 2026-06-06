# LLM 客户端协议 + MockLLM。MockLLM 是 A/B/C 并行的解耦器：契约 + Mock 一就位，三线全速跑。
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, Union


@dataclass
class Message:
    role: str  # system / user / assistant
    content: str


@dataclass
class LLMResponse:
    text: str
    tokens: int


class LLMClient(Protocol):
    def complete(self, messages: list[Message], **params) -> LLMResponse: ...


def estimate_tokens(text: str) -> int:
    # 粗估：约 4 字符 1 token，够 V1 的成本指标用；接真实模型时换成 provider 返回值
    return max(1, len(text) // 4)


# responder：根据对话动态生成回复；或给一个 list 按调用顺序返回
Responder = Union[Callable[[list[Message]], str], list[str]]


class MockLLM:
    """不接真实模型，按注入的 responder 返回。

    - responder 是 Callable[[list[Message]], str]：根据对话内容动态决定回复（端到端常用）
    - responder 是 list[str]：按调用顺序依次返回，耗尽即报错（脚本化测试常用）
    """

    def __init__(self, responder: Responder):
        if isinstance(responder, list):
            self._queue: list[str] | None = list(responder)
            self._fn: Callable[[list[Message]], str] | None = None
        else:
            self._fn = responder
            self._queue = None
        self.calls = 0

    def complete(self, messages: list[Message], **params) -> LLMResponse:
        self.calls += 1
        if self._fn is not None:
            text = self._fn(messages)
        else:
            assert self._queue is not None
            if not self._queue:
                raise RuntimeError("MockLLM 脚本响应已耗尽")
            text = self._queue.pop(0)
        prompt_tokens = sum(estimate_tokens(m.content) for m in messages)
        return LLMResponse(text=text, tokens=prompt_tokens + estimate_tokens(text))
