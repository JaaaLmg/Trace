from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CanonicalPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str
    old: str = Field(min_length=1)
    new: str

    @field_validator("file")
    @classmethod
    def _file_is_project_relative(cls, value: str) -> str:
        normalized = value.replace("\\", "/").strip()
        if not normalized:
            raise ValueError("file cannot be empty")
        if normalized.startswith("/") or normalized.startswith("//") or (len(normalized) >= 2 and normalized[1] == ":"):
            raise ValueError("file must be relative to the project root")
        if any(part == ".." for part in normalized.split("/")):
            raise ValueError("file must not contain parent-directory traversal")
        return normalized


class EvalDatasetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    name: str
    version: str
    description: str | None = None
    project_snapshot_ids: list[str] = Field(default_factory=list)


class EvalTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    project_snapshot_id: str
    target_scope: dict = Field(default_factory=dict)
    goal: str
    expected_capabilities: list = Field(default_factory=list)


class SeededBugCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    bug_type: str
    description: str
    expected_detection: str


class BugVariantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    variant_name: str
    canonical_kind: str = "patch"
    patch: CanonicalPatch
    mutated_snapshot_id: str | None = None
    ground_truth: dict = Field(default_factory=dict)


class EvalDatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    version: str
    description: str | None = None
    project_snapshot_ids: list
    created_at: datetime


class EvalTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    project_snapshot_id: str
    target_scope: dict
    goal: str
    expected_capabilities: list
    created_at: datetime


class SeededBugOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    eval_task_id: str
    bug_type: str
    description: str
    expected_detection: str
    created_at: datetime


class BugVariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    seeded_bug_id: str
    variant_name: str
    canonical_kind: str
    patch_artifact_id: str | None = None
    mutated_snapshot_id: str | None = None
    ground_truth: dict
    created_at: datetime


class SeededBugDetailOut(SeededBugOut):
    variants: list[BugVariantOut] = Field(default_factory=list)


class EvalTaskDetailOut(EvalTaskOut):
    seeded_bugs: list[SeededBugDetailOut] = Field(default_factory=list)


class EvalDatasetDetailOut(EvalDatasetOut):
    tasks: list[EvalTaskDetailOut] = Field(default_factory=list)
