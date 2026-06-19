from __future__ import annotations

from typing import Any
from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.evaluation import LlmOverride, MutationDiscoveryAuditReportContract


_RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def validate_resource_id(value: str | None) -> str | None:
    if value is None:
        return None
    if not _RESOURCE_ID_RE.fullmatch(value):
        raise ValueError("id must be 1-64 chars: letters, digits, dot, underscore or hyphen")
    return value


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

    @field_validator("id")
    @classmethod
    def _id_is_safe(cls, value: str | None) -> str | None:
        return validate_resource_id(value)


class EvalTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    project_snapshot_id: str
    target_scope: dict = Field(default_factory=dict)
    goal: str
    expected_capabilities: list = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _id_is_safe(cls, value: str | None) -> str | None:
        return validate_resource_id(value)


class SeededBugCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    bug_type: str
    description: str
    expected_detection: str

    @field_validator("id")
    @classmethod
    def _id_is_safe(cls, value: str | None) -> str | None:
        return validate_resource_id(value)


class BugVariantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    variant_name: str
    canonical_kind: str = "patch"
    patch: CanonicalPatch
    mutated_snapshot_id: str | None = None
    ground_truth: dict = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _id_is_safe(cls, value: str | None) -> str | None:
        return validate_resource_id(value)


class MutationDiscoveryDryRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_seed: int = Field(default=0, ge=0)
    max_selected: int = Field(default=20, ge=0)
    target_scope_override: dict[str, Any] | list[Any] | None = None


class MutationProbeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_kind: str
    probe: str
    clean_value: Any
    buggy_value: Any

    @field_validator("target_kind", "probe")
    @classmethod
    def _required_text_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("probe target_kind and expression cannot be blank")
        return value


class MutationCandidateConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_report: MutationDiscoveryAuditReportContract
    candidate_id: str
    probe: MutationProbeSpec
    seeded_bug_id: str | None = None
    variant_id: str | None = None
    bug_type: str = "auto_mutation"
    description: str | None = None
    expected_detection: str | None = None
    variant_name: str | None = None

    @field_validator("seeded_bug_id", "variant_id")
    @classmethod
    def _id_is_safe(cls, value: str | None) -> str | None:
        return validate_resource_id(value)

    @field_validator("candidate_id", "bug_type")
    @classmethod
    def _required_text_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("candidate_id and bug_type cannot be blank")
        return value


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


class ExperimentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    name: str
    dataset_id: str
    strategy_version_ids: list[str] = Field(min_length=1)
    repeat_count: int = Field(default=1, ge=1)
    llm_override: LlmOverride | None = None

    @field_validator("id")
    @classmethod
    def _id_is_safe(cls, value: str | None) -> str | None:
        return validate_resource_id(value)


class ExperimentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    dataset_id: str
    repeat_count: int
    llm_override: dict | None = None
    status: str
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    strategy_version_ids: list[str] = Field(default_factory=list)


class ExperimentCleanRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    experiment_id: str
    eval_task_id: str
    strategy_version_id: str
    repeat_index: int
    clean_run_id: str
    generated_test_set_artifact_id: str
    false_positive: bool
    clean_metrics: dict
    created_at: datetime


class TestReplayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    experiment_clean_run_id: str
    generated_test_set_artifact_id: str
    target_snapshot_id: str
    bug_variant_id: str | None = None
    status: str
    pytest_summary: dict
    replay_mode: str
    llm_calls: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
