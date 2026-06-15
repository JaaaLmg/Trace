from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StrategyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    workflow_type: str
    strategy_id: str | None = None


class PromptVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    content: dict
    source_ref: str | None = None


class ToolSchemaVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    schema_payload: dict


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
