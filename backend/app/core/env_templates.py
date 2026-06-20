from __future__ import annotations

import re
from typing import Any

REDACTED_ENV_VALUE = "<REDACTED>"

_SECRET_ENV_TOKENS = ("api_key", "apikey", "secret", "token", "password", "authorization")
_PLACEHOLDER_RE = re.compile(r"^(?:\$\{[A-Za-z_][A-Za-z0-9_]*\}|<[A-Za-z_][A-Za-z0-9_]*>)$")
_SECRET_VALUE_TOKENS = (
    "bearer ",
    "sk-",
    "ghp_",
    "github_pat_",
    "xoxb-",
    "xoxp-",
    "eyj",
)


def env_key_looks_secret(key: Any) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return any(token in normalized for token in _SECRET_ENV_TOKENS)


def env_value_is_allowed_placeholder(value: Any) -> bool:
    if value is None or value == "":
        return True
    return isinstance(value, str) and _PLACEHOLDER_RE.fullmatch(value) is not None


def env_value_looks_secret(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    return any(token in lowered for token in _SECRET_VALUE_TOKENS)


def reject_secret_env_template(env_template: dict[str, Any]) -> None:
    for key, value in env_template.items():
        if env_key_looks_secret(key):
            raise ValueError(f"env_template key {key!r} looks like a secret and must not be persisted")
        if env_value_is_allowed_placeholder(value):
            continue
        if not isinstance(value, str):
            raise ValueError(f"env_template value for {key!r} must be empty or a placeholder")
        if env_value_looks_secret(value):
            raise ValueError(f"env_template value for {key!r} looks like a secret and must not be persisted")
        raise ValueError(f"env_template value for {key!r} must be empty or a placeholder")


def sanitize_env_template(env_template: dict[str, Any] | None) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in dict(env_template or {}).items():
        if env_key_looks_secret(key):
            continue
        sanitized[str(key)] = value if env_value_is_allowed_placeholder(value) else REDACTED_ENV_VALUE
    return sanitized
