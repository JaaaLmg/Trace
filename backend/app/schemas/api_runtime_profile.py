from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RuntimeProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    python_version: str | None = None
    install_command: str | None = None
    test_command: str
    env_template: dict
    resource_limits: dict
    network_policy: str
    created_at: datetime
    updated_at: datetime
