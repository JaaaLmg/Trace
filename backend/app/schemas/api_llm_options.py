from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class LlmOptionOut(BaseModel):
    id: str
    label: str
    kind: Literal["mock", "configured"]
    provider: str
    model: str
    is_mock: bool
    selectable: bool
    credential_status: Literal["not_required", "configured", "missing_api_key"]
    config_source: Literal["built_in", "runtime_config"]
    base_url_configured: bool = False
    reason: str | None = None


class LlmOptionsOut(BaseModel):
    default_option_id: str
    config_status: Literal["ok", "missing", "error"]
    config_error: str | None = None
    options: list[LlmOptionOut]
