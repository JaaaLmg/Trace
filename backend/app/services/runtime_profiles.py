from __future__ import annotations

import platform

from app.core.ids import new_id
from app.models.runtime_profile import RuntimeProfile
from app.repositories.runtime_profiles import add_runtime_profile, list_runtime_profiles_for_project
from app.repositories.projects import get_project
from sqlalchemy.orm import Session

# V2 §6.1：network_policy 至少支持这三种。
_ALLOWED_NETWORK_POLICIES = {"default", "disabled", "install_only"}


def _default_test_command() -> str:
    return "python -m pytest tests -q --rootdir . -p no:cacheprovider"


def create_runtime_profile(
    session: Session,
    *,
    project_id: str,
    name: str,
    test_command: str | None = None,
    python_version: str | None = None,
    install_command: str | None = None,
    env_template: dict | None = None,
    resource_limits: dict | None = None,
    network_policy: str = "default",
) -> RuntimeProfile:
    if get_project(session, project_id) is None:
        raise ValueError("project not found")
    if network_policy not in _ALLOWED_NETWORK_POLICIES:
        raise ValueError(f"network_policy must be one of {sorted(_ALLOWED_NETWORK_POLICIES)}")
    profile = RuntimeProfile(
        id=new_id(),
        project_id=project_id,
        name=name,
        python_version=python_version or platform.python_version(),
        install_command=install_command,
        test_command=test_command or _default_test_command(),
        env_template=env_template or {},
        resource_limits=resource_limits or {"enforced": False},
        network_policy=network_policy,
    )
    return add_runtime_profile(session, profile)


def ensure_default_runtime_profile(session: Session, *, project_id: str) -> RuntimeProfile:
    existing = list_runtime_profiles_for_project(session, project_id)
    if existing:
        return existing[0]
    profile = RuntimeProfile(
        id=new_id(),
        project_id=project_id,
        name="Default Local Subprocess",
        python_version=platform.python_version(),
        install_command=None,
        test_command=_default_test_command(),
        env_template={},
        resource_limits={"enforced": False},
        network_policy="default",
    )
    return add_runtime_profile(session, profile)
