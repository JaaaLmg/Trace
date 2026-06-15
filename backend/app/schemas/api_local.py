from __future__ import annotations

from pydantic import BaseModel


class DirectoryPickRequest(BaseModel):
    initial_path: str | None = None
    title: str | None = None


class DirectoryPickOut(BaseModel):
    path: str | None
    cancelled: bool
