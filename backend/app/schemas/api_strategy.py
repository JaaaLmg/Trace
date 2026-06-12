from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrategyVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    workflow_type: str
    model_provider: str
    model_name: str
    model_params: dict
    allow_reflection: bool
    max_tool_calls: int
    prompt_ref: str
    tool_schema_ref: str
