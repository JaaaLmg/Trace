from typing import Literal

from pydantic import BaseModel, Field

WorkflowType = Literal["direct", "plan_execute", "react_reflection"]


class StrategyVersionSpec(BaseModel):
    id: str
    strategy_id: str | None = None
    name: str
    version: str | None = None
    workflow_type: WorkflowType
    model_provider: str = "mock"
    model_name: str = "mock-1"
    model_params: dict = Field(default_factory=dict)
    temperature: float | None = None
    allow_reflection: bool = False
    max_tool_calls: int = 12
    prompt_version_id: str | None = None
    tool_schema_version_id: str | None = None
    prompt_ref: str = "v1"
    tool_schema_ref: str = "v1"
    is_locked: bool = False
