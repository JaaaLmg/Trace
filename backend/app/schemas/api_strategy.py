from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrategyVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    prompt_version_id: str
    tool_schema_version_id: str
    model_provider: str = "mock"
    model_name: str = "mock-1"
    model_params: dict = Field(default_factory=dict)
    temperature: float | None = Field(default=None, ge=0)
    allow_reflection: bool = False
    max_tool_calls: int = Field(default=12, ge=1)


class StrategyVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    strategy_id: str | None = None
    name: str
    version: str | None = None
    workflow_type: str
    model_provider: str
    model_name: str
    model_params: dict
    temperature: float | None = None
    allow_reflection: bool
    max_tool_calls: int
    prompt_version_id: str | None = None
    tool_schema_version_id: str | None = None
    prompt_ref: str
    tool_schema_ref: str
    is_locked: bool
