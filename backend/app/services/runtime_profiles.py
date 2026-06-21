from __future__ import annotations

import platform
from typing import Any

from app.core.env_templates import reject_secret_env_template, sanitize_env_template
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
from app.tools.executor import docker_available, executor_capabilities_from_snapshot, _parse_test_command
from sqlalchemy.orm import Session

# V2 §6.1：network_policy 至少支持这三种。
_ALLOWED_NETWORK_POLICIES = {"default", "disabled", "install_only"}
_ALLOWED_EXECUTORS = {"local_subprocess", "docker"}


def _coerce_int(value: Any, *, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc


def _coerce_float(value: Any, *, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc


def _default_test_command() -> str:
    return "python -m pytest tests -q --rootdir . -p no:cacheprovider"


def _validate_profile_config(
    *,
    executor: str,
    image: str | None,
    timeout_seconds: int | None,
    env_template: dict | None,
    resource_limits: dict | None,
    replay_policy: dict | None,
    network_policy: str,
) -> None:
    if executor not in _ALLOWED_EXECUTORS:
        raise ValueError(f"executor must be one of {sorted(_ALLOWED_EXECUTORS)}")
    if network_policy not in _ALLOWED_NETWORK_POLICIES:
        raise ValueError(f"network_policy must be one of {sorted(_ALLOWED_NETWORK_POLICIES)}")
    if timeout_seconds is not None and _coerce_int(timeout_seconds, field="timeout_seconds") < 1:
        raise ValueError("timeout_seconds must be positive")
    reject_secret_env_template(dict(env_template or {}))
    limits = dict(resource_limits or {})
    if executor == "docker" and not (image or "").strip():
        raise ValueError("docker runtime profile requires image")
    if executor == "local_subprocess":
        if limits.get("enforced") is True:
            raise ValueError("local_subprocess cannot claim enforced resource limits")
        if network_policy != "default":
            raise ValueError("local_subprocess cannot enforce non-default network_policy")
    policy = dict(replay_policy or {})
    for key in ("replay_concurrency", "max_retries"):
        if key in policy and _coerce_int(policy[key], field=key) < 0:
            raise ValueError(f"{key} must be non-negative")
    if "replay_concurrency" in policy and _coerce_int(policy["replay_concurrency"], field="replay_concurrency") < 1:
        raise ValueError("replay_concurrency must be >= 1")
    if (
        "retry_backoff_seconds" in policy
        and _coerce_float(policy["retry_backoff_seconds"], field="retry_backoff_seconds") < 0
    ):
        raise ValueError("retry_backoff_seconds must be non-negative")


def _normalize_replay_policy(resource_limits: dict | None, replay_policy: dict | None) -> dict:
    limits = dict(resource_limits or {})
    policy = dict(replay_policy or {})
    if "replay_concurrency" not in policy and limits.get("replay_concurrency") is not None:
        policy["replay_concurrency"] = _coerce_int(limits["replay_concurrency"], field="replay_concurrency")
    policy.setdefault("replay_concurrency", 1)
    policy.setdefault("max_retries", 0)
    policy.setdefault("retry_backoff_seconds", 0)
    policy["replay_concurrency"] = max(1, _coerce_int(policy["replay_concurrency"], field="replay_concurrency"))
    policy["max_retries"] = max(0, _coerce_int(policy["max_retries"], field="max_retries"))
    policy["retry_backoff_seconds"] = max(
        0,
        _coerce_float(policy["retry_backoff_seconds"], field="retry_backoff_seconds"),
    )
    return policy


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
    replay_policy: dict | None = None,
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
        replay_policy=replay_policy,
        network_policy=network_policy,
    )
    resource_payload = dict(resource_limits or {"enforced": False})
    if timeout_seconds is not None:
        resource_payload["timeout_seconds"] = int(timeout_seconds)
    replay_payload = _normalize_replay_policy(resource_payload, replay_policy)
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
        replay_policy=replay_payload,
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
        "replay_policy": updates.get("replay_policy", profile.replay_policy),
        "network_policy": updates.get("network_policy", profile.network_policy),
    }
    _validate_profile_config(**next_values)
    if "resource_limits" in updates or "replay_policy" in updates:
        updates["replay_policy"] = _normalize_replay_policy(
            updates.get("resource_limits", profile.resource_limits),
            updates.get("replay_policy", profile.replay_policy),
        )

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
        "replay_policy",
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


def preflight_runtime_profile_payload(payload: dict[str, Any]) -> dict:
    executor = str(payload.get("executor") or "local_subprocess")
    image = payload.get("image")
    network_policy = str(payload.get("network_policy") or "default")
    resource_limits = dict(payload.get("resource_limits") or {})
    test_command = str(payload.get("test_command") or _default_test_command())
    checks: list[dict[str, Any]] = []

    def add(name: str, status: str, message: str, **extra: Any) -> None:
        checks.append({"name": name, "status": status, "message": message, **extra})

    replay_policy: dict[str, Any] = {}
    try:
        replay_policy = _normalize_replay_policy(
            resource_limits,
            payload.get("replay_policy") if isinstance(payload.get("replay_policy"), dict) else {},
        )
        _validate_profile_config(
            executor=executor,
            image=str(image) if image is not None else None,
            timeout_seconds=(resource_limits.get("timeout_seconds") if resource_limits else payload.get("timeout_seconds")),
            env_template=dict(payload.get("env_template") or {}),
            resource_limits=resource_limits,
            replay_policy=replay_policy,
            network_policy=network_policy,
        )
        add("profile_contract", "passed", "runtime profile contract is valid")
    except Exception as exc:
        add("profile_contract", "failed", str(exc))

    interpreter, passthrough_args = _parse_test_command(test_command)
    add(
        "test_command",
        "passed",
        "pytest command parsed; structural flags remain executor-controlled",
        interpreter=interpreter,
        passthrough_args=passthrough_args,
    )
    caps = executor_capabilities_from_snapshot(
        {
            "executor": executor,
            "image": image,
            "test_command": test_command,
            "network_policy": network_policy,
            "resource_limits": resource_limits,
        }
    ) if not (executor == "docker" and not image) else {}
    if caps:
        add("executor_capabilities", "passed", "executor capabilities resolved", capabilities=caps)
    if executor == "local_subprocess":
        add("local_subprocess_sandbox", "warning", "local_subprocess is not a security sandbox")
    if executor == "docker":
        docker_ok, docker_reason = docker_available()
        add(
            "docker_available",
            "passed" if docker_ok else "failed",
            "docker CLI and daemon are available" if docker_ok else str(docker_reason or "docker is unavailable"),
        )
        if not image:
            add("docker_image", "failed", "docker runtime profile requires image")
        else:
            add("docker_image", "warning", "image availability is checked during execution or pull policy")

    failed = any(check["status"] == "failed" for check in checks)
    warning = any(check["status"] == "warning" for check in checks)
    return {
        "status": "failed" if failed else "warning" if warning else "passed",
        "checks": checks,
        "replay_policy": replay_policy,
        "audit_only_limitations": [
            item
            for item in [
                "preflight does not execute generated tests",
                "local_subprocess is not a security sandbox" if executor == "local_subprocess" else "",
            ]
            if item
        ],
    }


def preflight_runtime_profile(session: Session, *, profile_id: str) -> dict:
    profile = get_runtime_profile(session, profile_id)
    if profile is None:
        raise ValueError("runtime profile not found")
    return preflight_runtime_profile_payload(
        {
            "executor": profile.executor,
            "image": profile.image,
            "working_dir": profile.working_dir,
            "test_command": profile.test_command,
            "env_template": profile.env_template,
            "resource_limits": profile.resource_limits,
            "replay_policy": profile.replay_policy,
            "network_policy": profile.network_policy,
            "artifact_policy": profile.artifact_policy,
            "cleanup_policy": profile.cleanup_policy,
        }
    )


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
        replay_policy={"replay_concurrency": 1, "max_retries": 0, "retry_backoff_seconds": 0},
        network_policy="default",
        artifact_policy={"retain": "evidence"},
        cleanup_policy={"mode": "manual", "keep_failed": True},
    )
    return add_runtime_profile(session, profile)
