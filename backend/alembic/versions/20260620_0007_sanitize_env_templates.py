"""sanitize env template secret values

Revision ID: 20260620_0007
Revises: 20260619_0006
Create Date: 2026-06-20
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import MetaData, Table, select

from app.core.env_templates import sanitize_env_template

revision = "20260620_0007"
down_revision = "20260619_0006"
branch_labels = None
depends_on = None


def _sanitize_snapshot(snapshot: dict | None) -> dict:
    clean = dict(snapshot or {})
    if "env_template" in clean:
        clean["env_template"] = sanitize_env_template(clean.get("env_template"))
        clean["env_keys"] = sorted(clean["env_template"].keys())
    return clean


def upgrade() -> None:
    connection = op.get_bind()
    metadata = MetaData()

    runtime_profiles = Table("runtime_profiles", metadata, autoload_with=connection)
    for row in connection.execute(select(runtime_profiles.c.id, runtime_profiles.c.env_template)):
        clean_env = sanitize_env_template(row.env_template)
        if clean_env != (row.env_template or {}):
            connection.execute(
                runtime_profiles.update()
                .where(runtime_profiles.c.id == row.id)
                .values(env_template=clean_env)
            )

    test_runs = Table("test_runs", metadata, autoload_with=connection)
    for row in connection.execute(select(test_runs.c.id, test_runs.c.runtime_snapshot)):
        clean_snapshot = _sanitize_snapshot(row.runtime_snapshot)
        if clean_snapshot != (row.runtime_snapshot or {}):
            connection.execute(
                test_runs.update()
                .where(test_runs.c.id == row.id)
                .values(runtime_snapshot=clean_snapshot)
            )

    test_replays = Table("test_replays", metadata, autoload_with=connection)
    for row in connection.execute(select(test_replays.c.id, test_replays.c.runtime_snapshot)):
        clean_snapshot = _sanitize_snapshot(row.runtime_snapshot)
        if clean_snapshot != (row.runtime_snapshot or {}):
            connection.execute(
                test_replays.update()
                .where(test_replays.c.id == row.id)
                .values(runtime_snapshot=clean_snapshot)
            )


def downgrade() -> None:
    # Redacted secret-looking values cannot be reconstructed safely.
    pass
