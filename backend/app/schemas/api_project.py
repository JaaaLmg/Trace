from __future__ import annotations

from pydantic import BaseModel


class ProjectCreateRequest(BaseModel):
    name: str
    local_path: str
    description: str | None = None


class SnapshotCreateRequest(BaseModel):
    root_path: str | None = None
