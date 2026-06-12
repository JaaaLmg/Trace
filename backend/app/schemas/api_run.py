from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class RunBudgetOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: int | None = Field(default=None, ge=1)
    allow_reflection: bool | None = None


class RunCreateRequest(BaseModel):
    snapshot_id: str
    strategy_version_id: str | None = None
    budget_override: RunBudgetOverride = Field(default_factory=RunBudgetOverride)
    output_options: dict = Field(default_factory=dict)


class AdoptionPatchRequest(BaseModel):
    adoption_status: str
    human_meaningfulness_score: int | None = None


class TestRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    test_plan_id: str
    retry_of_run_id: str | None = None
    project_snapshot_id: str
    runtime_profile_id: str | None = None
    strategy_version_id: str
    runtime_snapshot: dict
    strategy_snapshot: dict
    status: str
    stage: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    total_tokens: int
    total_cost: Decimal | None = None
    tool_call_count: int
    pytest_summary: dict
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime


class TraceStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    attempt_id: str | None = None
    step_index: int
    step_type: str
    name: str
    input_summary: str | None = None
    output_summary: str | None = None
    tool_name: str | None = None
    payload: dict | None = None
    tokens: int | None = None
    duration_ms: int | None = None
    status: str
    error: str | None = None
    created_at: datetime


class RunEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    stage: str | None = None
    event_type: str
    status_before: str | None = None
    status_after: str | None = None
    message: str | None = None
    created_at: datetime


class RunAttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_plan_item_id: str
    attempt_no: int
    kind: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    pytest_exit_code: int | None = None
    error_code: str | None = None
    reflection_reason: str | None = None


class PytestCaseResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    attempt_id: str
    generated_test_case_id: str | None = None
    nodeid: str
    mapping_status: str
    status: str
    duration_ms: int
    failure_type: str | None = None
    failure_message: str | None = None
    traceback_hash: str | None = None
    stdout_excerpt: str | None = None
    stderr_excerpt: str | None = None
    is_collection_error: bool


class RunArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    attempt_id: str | None = None
    runner_job_id: str | None = None
    artifact_type: str
    uri: str
    content_hash: str | None = None
    size_bytes: int | None = None
    metadata_json: dict
    created_at: datetime


class TestReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    summary: str
    metrics: dict
    risk_notes: str | None = None
    markdown_artifact_id: str | None = None
    json_artifact_id: str | None = None
    markdown_uri: str | None = None
    json_uri: str | None = None
    created_at: datetime


class GeneratedTestCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    file_id: str
    nodeid: str | None = None
    test_name: str
    start_line: int
    end_line: int
    target_route: str | None = None
    target_function: str | None = None
    assertion_summary: str | None = None
    source_strategy_version_id: str | None = None
    adoption_status: str
    human_meaningfulness_score: int | None = None
    rule_flags: list
