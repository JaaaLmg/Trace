from __future__ import annotations

import platform
from typing import Any

from app.core.ids import new_id
from app.models.runtime_profile import RuntimeProfile
from datetime import datetime, timezone

from app.repositories.runtime_profiles import (
    add_runtime_profile,
    get_runtime_profile,
    list_active_runtime_profiles_for_project,
    list_runtime_profiles_for_project,
)
from app.repositories.projects import get_project
from sqlalchemy.orm import Session

# V2 §6.1：network_policy 至少支持这三种。
_ALLOWED_NETWORK_POLICIES = {"default", "disabled", "install_only"}
_ALLOWED_EXECUTORS = {"local_subprocess", "docker"}
_SECRET_ENV_TOKENS = ("api_key", "apikey", "secret", "token", "password", "authorization")


def _default_test_command() -> str:
    return "python -m pytest tests -q --rootdir . -p no:cacheprovider"


def _reject_secret_env(env_template: dict[str, Any]) -> None:
    for key in env_template:
        normalized = str(key).lower().replace("-", "_")
        if any(token in normalized for token in _SECRET_ENV_TOKENS):
            raise ValueError(f"env_template key {key!r} looks like a secret and must not be persisted")


def _validate_profile_config(
    *,
    executor: str,
    image: str | None,
    timeout_seconds: int | None,
    env_template: dict | None,
    resource_limits: dict | None,
    network_policy: str,
) -> None:
    if executor not in _ALLOWED_EXECUTORS:
        raise ValueError(f"executor must be one of {sorted(_ALLOWED_EXECUTORS)}")
    if network_policy not in _ALLOWED_NETWORK_POLICIES:
        raise ValueError(f"network_policy must be one of {sorted(_ALLOWED_NETWORK_POLICIES)}")
    if timeout_seconds is not None and int(timeout_seconds) < 1:
        raise ValueError("timeout_seconds must be positive")
    _reject_secret_env(dict(env_template or {}))
    limits = dict(resource_limits or {})
    if executor == "docker" and not (image or "").strip():
        raise ValueError("docker runtime profile requires image")
    if executor == "local_subprocess":
        if limits.get("enforced") is True:
            raise ValueError("local_subprocess cannot claim enforced resource limits")
        if network_policy != "default":
            raise ValueError("local_subprocess cannot enforce non-default network_policy")


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
    executor: str = "local_subprocess",
    image: str | None = None,
    working_dir: str | None = None,
    timeout_seconds: int | None = None,
    artifact_policy: dict | None = None,
    cleanup_policy: dict | None = None,
) -> RuntimeProfile:
    if get_project(session, project_id) is None:
        raise ValueError("project not found")
    _validate_profile_config(
        executor=executor,
        image=image,
        timeout_seconds=timeout_seconds,
        env_template=env_template,
        resource_limits=resource_limits,
        network_policy=network_policy,
    )
    resource_payload = dict(resource_limits or {"enforced": False})
    if timeout_seconds is not None:
        resource_payload["timeout_seconds"] = int(timeout_seconds)
    profile = RuntimeProfile(
        id=new_id(),
        project_id=project_id,
        name=name,
        executor=executor,
        image=image,
        working_dir=working_dir,
        python_version=python_version or platform.python_version(),
        install_command=install_command,
        test_command=test_command or _default_test_command(),
        env_template=env_template or {},
        resource_limits=resource_payload,
        network_policy=network_policy,
        artifact_policy=artifact_policy or {"retain": "evidence"},
        cleanup_policy=cleanup_policy or {"mode": "manual", "keep_failed": True},
    )
    return add_runtime_profile(session, profile)


def update_runtime_profile(
    session: Session,
    *,
    profile_id: str,
    updates: dict[str, Any],
) -> RuntimeProfile:
    profile = get_runtime_profile(session, profile_id)
    if profile is None:
        raise ValueError("runtime profile not found")
    if profile.archived_at is not None:
        raise ValueError("archived runtime profile cannot be updated")

    next_values = {
        "executor": updates.get("executor", profile.executor),
        "image": updates.get("image", profile.image),
        "timeout_seconds": updates.get("timeout_seconds", (profile.resource_limits or {}).get("timeout_seconds")),
        "env_template": updates.get("env_template", profile.env_template),
        "resource_limits": updates.get("resource_limits", profile.resource_limits),
        "network_policy": updates.get("network_policy", profile.network_policy),
    }
    _validate_profile_config(**next_values)

    nullable_fields = {"image", "working_dir", "python_version", "install_command"}
    for field in (
        "name",
        "executor",
        "image",
        "working_dir",
        "test_command",
        "python_version",
        "install_command",
        "env_template",
        "resource_limits",
        "network_policy",
        "artifact_policy",
        "cleanup_policy",
    ):
        if field not in updates:
            continue
        if updates[field] is not None or field in nullable_fields:
            setattr(profile, field, updates[field])
    if "timeout_seconds" in updates and updates["timeout_seconds"] is not None:
        limits = dict(profile.resource_limits or {})
        limits["timeout_seconds"] = int(updates["timeout_seconds"])
        profile.resource_limits = limits
    profile.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(profile)
    return profile


def archive_runtime_profile(session: Session, *, profile_id: str) -> RuntimeProfile:
    profile = get_runtime_profile(session, profile_id)
    if profile is None:
        raise ValueError("runtime profile not found")
    if profile.archived_at is None:
        profile.archived_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(profile)
    return profile


def ensure_default_runtime_profile(session: Session, *, project_id: str) -> RuntimeProfile:
    existing = list_active_runtime_profiles_for_project(session, project_id)
    if existing:
        return existing[0]
    profile = RuntimeProfile(
        id=new_id(),
        project_id=project_id,
        name="Default Local Subprocess",
        executor="local_subprocess",
        image=None,
        working_dir=None,
        python_version=platform.python_version(),
        install_command=None,
        test_command=_default_test_command(),
        env_template={},
        resource_limits={"enforced": False, "timeout_seconds": 120},
        network_policy="default",
        artifact_policy={"retain": "evidence"},
        cleanup_policy={"mode": "manual", "keep_failed": True},
    )
    return add_runtime_profile(session, profile)
