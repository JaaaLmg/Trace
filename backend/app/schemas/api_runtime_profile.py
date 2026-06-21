from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.core.env_templates import sanitize_env_template


class RuntimeProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    executor: str = "local_subprocess"
    image: str | None = None
    working_dir: str | None = None
    test_command: str | None = None
    python_version: str | None = None
    install_command: str | None = None
    env_template: dict = Field(default_factory=dict)
    resource_limits: dict = Field(default_factory=dict)
    replay_policy: dict = Field(default_factory=dict)
    network_policy: str = "default"
    timeout_seconds: int | None = Field(default=None, ge=1)
    artifact_policy: dict = Field(default_factory=dict)
    cleanup_policy: dict = Field(default_factory=dict)


class RuntimeProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    executor: str | None = None
    image: str | None = None
    working_dir: str | None = None
    test_command: str | None = None
    python_version: str | None = None
    install_command: str | None = None
    env_template: dict | None = None
    resource_limits: dict | None = None
    replay_policy: dict | None = None
    network_policy: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=1)
    artifact_policy: dict | None = None
    cleanup_policy: dict | None = None


class RuntimeProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    executor: str
    image: str | None = None
    working_dir: str | None = None
    python_version: str | None = None
    install_command: str | None = None
    test_command: str
    env_template: dict
    resource_limits: dict
    replay_policy: dict
    network_policy: str
    artifact_policy: dict
    cleanup_policy: dict
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_serializer("env_template")
    def serialize_env_template(self, env_template: dict) -> dict:
        return sanitize_env_template(env_template)


class DatasetRuntimeBindingTaskOut(BaseModel):
    task_id: str
    project_id: str
    project_snapshot_id: str


class DatasetRuntimeBindingProjectOut(BaseModel):
    project_id: str
    project_name: str | None = None
    profiles: list[RuntimeProfileOut] = Field(default_factory=list)


class DatasetRuntimeBindingManifestOut(BaseModel):
    dataset_id: str
    multi_project: bool
    tasks: list[DatasetRuntimeBindingTaskOut] = Field(default_factory=list)
    projects: list[DatasetRuntimeBindingProjectOut] = Field(default_factory=list)
