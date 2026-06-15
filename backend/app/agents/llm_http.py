# LLM provider 的 HTTP 调用层：瞬态错误（连接抖动 / 429 限流 / 5xx）有限次退避重试，
# 永久错误（4xx）或重试耗尽都包成 TraceError(LLM_PROVIDER_ERROR)——让上层 think() 能 catch、
# 落 error trace、累计 token，而不是抛裸 RuntimeError 被 orchestrator 兜成笼统的内部错误。
from __future__ import annotations

import re
import time
from typing import Optional

import httpx

from app.core.errors import ErrorCode, TraceError

# 这些状态码是「再试一次可能就好」的瞬态错误：429 限流、5xx 服务端抖动。
# 其余 4xx（401 鉴权 / 400 参数）是配置问题，重试无意义，快速失败。
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# LLM 调用默认输出上限。Responses API 的 reasoning 模型会把推理 token 算进这个预算，
# 4096 容易被推理吃光导致空输出，两个 adapter 统一留足余量。
DEFAULT_MAX_OUTPUT_TOKENS = 8192

_MASKED_SECRET_RE = re.compile(r"\b[A-Za-z0-9_-]{2,}\*{4,}[A-Za-z0-9_-]*\b")
_BEARER_SECRET_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)


def redact(text: str, secret: Optional[str]) -> str:
    # key 不进日志/错误信息：把 body 里出现的密钥替换掉
    if secret:
        text = text.replace(secret, "[redacted]")
    text = _MASKED_SECRET_RE.sub("[redacted]", text)
    text = _BEARER_SECRET_RE.sub("Bearer [redacted]", text)
    return text


def format_http_error(label: str, resp: httpx.Response, api_key: Optional[str]) -> str:
    status = f"{resp.status_code} {resp.reason_phrase}".strip()
    body = redact(resp.text.strip(), api_key)
    if len(body) > 500:
        body = body[:497] + "..."
    if body:
        return f"{label} HTTP {status}: {body}"
    return f"{label} HTTP {status}"


def _retry_after_seconds(resp: httpx.Response) -> Optional[float]:
    # 429/503 常带 Retry-After。只认秒数形式；HTTP-date 形式忽略，退回指数退避
    raw = getattr(resp, "headers", {}).get("Retry-After") if hasattr(resp, "headers") else None
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def request_json(
    client,
    method: str,
    url: str,
    *,
    headers: dict,
    json_body: Optional[dict] = None,
    error_label: str,
    api_key: Optional[str],
    max_retries: int = 2,
    backoff: float = 0.5,
) -> dict:
    """发请求并返回 JSON。瞬态错误退避重试；永久错误 / 重试耗尽抛 TraceError(LLM_PROVIDER_ERROR)。"""
    for attempt in range(max_retries + 1):
        try:
            if method == "GET":
                resp = client.get(url, headers=headers)
            else:
                resp = client.post(url, headers=headers, json=json_body)
        except httpx.HTTPError as e:
            # 传输层抖动（连接失败 / 超时 / 读错）：可重试，耗尽才抛
            if attempt < max_retries:
                time.sleep(backoff * (2**attempt))
                continue
            raise TraceError(
                ErrorCode.LLM_PROVIDER_ERROR, f"{error_label} 请求失败：{type(e).__name__}: {e}"
            ) from e

        status = getattr(resp, "status_code", 200)
        if status in _RETRYABLE_STATUS and attempt < max_retries:
            wait = _retry_after_seconds(resp)
            time.sleep(wait if wait is not None else backoff * (2**attempt))
            continue
        if hasattr(resp, "raise_for_status"):
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise TraceError(ErrorCode.LLM_PROVIDER_ERROR, format_http_error(error_label, resp, api_key)) from e
        return resp.json()

    # 不可达：循环每一轮要么 return 要么在最后一次 attempt 抛出
    raise TraceError(ErrorCode.LLM_PROVIDER_ERROR, f"{error_label} 请求失败：重试 {max_retries} 次仍未成功")
