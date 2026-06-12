from __future__ import annotations

from pydantic import BaseModel, Field


class RunCreateRequest(BaseModel):
    snapshot_id: str
    strategy_version_id: str | None = None
    budget_override: dict = Field(default_factory=dict)
    output_options: dict = Field(default_factory=dict)


class AdoptionPatchRequest(BaseModel):
    adoption_status: str
    human_meaningfulness_score: int | None = None
