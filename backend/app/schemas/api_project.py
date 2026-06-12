from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProjectCreateRequest(BaseModel):
    name: str
    local_path: str
    description: str | None = None


class SnapshotCreateRequest(BaseModel):
    root_path: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None = None
    source_type: str
    repo_url: str | None = None
    local_path: str
    default_branch: str | None = None
    language: str
    framework: str
    status: str
    created_at: datetime
    updated_at: datetime


class ProjectSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    source_kind: str
    root_path: str
    content_hash: str | None = None
    created_at: datetime
