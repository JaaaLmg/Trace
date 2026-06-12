from __future__ import annotations

from app.db.settings import _resolve_setting


def get_redis_url() -> str:
    return _resolve_setting("TRACE_REDIS_URL", "redis://127.0.0.1:6379/0")
