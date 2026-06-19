"""v22 executor runtime replay evidence

Revision ID: 20260619_0006
Revises: 20260616_0005
Create Date: 2026-06-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260619_0006"
down_revision = "20260616_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runtime_profiles", sa.Column("executor", sa.String(length=32), nullable=False, server_default="local_subprocess"))
    op.add_column("runtime_profiles", sa.Column("image", sa.String(length=255), nullable=True))
    op.add_column("runtime_profiles", sa.Column("working_dir", sa.String(length=255), nullable=True))
    op.add_column(
        "runtime_profiles",
        sa.Column("artifact_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "runtime_profiles",
        sa.Column("cleanup_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column("runtime_profiles", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("experiments", sa.Column("runtime_profile_id", sa.String(length=36), nullable=True))
    op.create_index("ix_experiments_runtime_profile_id", "experiments", ["runtime_profile_id"])
    op.create_foreign_key(
        "experiments_runtime_profile_id_fkey",
        "experiments",
        "runtime_profiles",
        ["runtime_profile_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.add_column(
        "test_replays",
        sa.Column("runtime_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "test_replays",
        sa.Column("executor_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "test_replays",
        sa.Column("workspace_manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column("test_replays", sa.Column("cache_key", sa.String(length=128), nullable=True))
    op.add_column("test_replays", sa.Column("cache_status", sa.String(length=32), nullable=False, server_default="miss"))
    op.add_column("test_replays", sa.Column("source_replay_id", sa.String(length=36), nullable=True))
    op.create_index("ix_test_replays_cache_key", "test_replays", ["cache_key"])
    op.create_foreign_key(
        "test_replays_source_replay_id_fkey",
        "test_replays",
        "test_replays",
        ["source_replay_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("test_replays_source_replay_id_fkey", "test_replays", type_="foreignkey")
    op.drop_index("ix_test_replays_cache_key", table_name="test_replays")
    op.drop_column("test_replays", "source_replay_id")
    op.drop_column("test_replays", "cache_status")
    op.drop_column("test_replays", "cache_key")
    op.drop_column("test_replays", "workspace_manifest")
    op.drop_column("test_replays", "executor_metadata")
    op.drop_column("test_replays", "runtime_snapshot")
    op.drop_constraint("experiments_runtime_profile_id_fkey", "experiments", type_="foreignkey")
    op.drop_index("ix_experiments_runtime_profile_id", table_name="experiments")
    op.drop_column("experiments", "runtime_profile_id")
    op.drop_column("runtime_profiles", "archived_at")
    op.drop_column("runtime_profiles", "cleanup_policy")
    op.drop_column("runtime_profiles", "artifact_policy")
    op.drop_column("runtime_profiles", "working_dir")
    op.drop_column("runtime_profiles", "image")
    op.drop_column("runtime_profiles", "executor")
