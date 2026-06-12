from __future__ import annotations

from pydantic import BaseModel, Field


class TestPlanCreateRequest(BaseModel):
    project_id: str
    name: str
    target_scope: list[str] = Field(default_factory=list)
    goal: str
    budget: dict = Field(default_factory=dict)
    output_options: dict = Field(default_factory=dict)
    default_strategy_version_id: str | None = None
