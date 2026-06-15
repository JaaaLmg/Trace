from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    workflow_type: str
    created_at: datetime


class PromptVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    version: str
    content: dict
    content_hash: str
    source_ref: str | None = None
    created_at: datetime


class ToolSchemaVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version: str
    schema_payload: dict = Field(validation_alias="schema_json")
    content_hash: str
    created_at: datetime
