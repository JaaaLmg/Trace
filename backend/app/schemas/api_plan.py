from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PlanBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: int | None = Field(default=None, ge=1)
    allow_reflection: bool | None = None


class TestPlanCreateRequest(BaseModel):
    project_id: str
    name: str
    target_scope: list[str] = Field(default_factory=list)
    goal: str
    budget: PlanBudget = Field(default_factory=PlanBudget)
    output_options: dict = Field(default_factory=dict)
    default_strategy_version_id: str | None = None


class TestPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    target_scope: list
    goal: str
    budget: dict
    output_options: dict
    default_strategy_version_id: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
