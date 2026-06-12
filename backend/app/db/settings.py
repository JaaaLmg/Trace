from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _resolve_setting(name: str, default: str | None = None) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    root = _repo_root()
    for env_name in (".env.local", ".env"):
        values = _load_env_file(root / env_name)
        if name in values:
            return values[name]
    return default


@dataclass(frozen=True)
class DatabaseSettings:
    database_url: str
    echo: bool = False


def get_database_settings() -> DatabaseSettings:
    database_url = _resolve_setting("TRACE_DB_URL")
    if not database_url:
        raise RuntimeError("TRACE_DB_URL 未配置；请在环境变量或仓库根目录 .env.local 中设置")
    return DatabaseSettings(
        database_url=database_url,
        echo=_resolve_setting("TRACE_DB_ECHO", "false").lower() == "true",
    )
