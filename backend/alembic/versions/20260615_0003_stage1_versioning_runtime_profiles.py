"""stage1 versioning and runtime profiles

Revision ID: 20260615_0003
Revises: 20260612_0002
Create Date: 2026-06-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260615_0003"
down_revision = "20260612_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("python_version", sa.String(length=64), nullable=True),
        sa.Column("install_command", sa.Text(), nullable=True),
        sa.Column("test_command", sa.Text(), nullable=False),
        sa.Column("env_template", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("resource_limits", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("network_policy", sa.String(length=32), nullable=False, server_default="default"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_runtime_profiles_project_id", "runtime_profiles", ["project_id"])

    op.create_table(
        "strategies",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("workflow_type", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    op.create_table(
        "tool_schema_versions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("schema_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    op.add_column("strategy_versions", sa.Column("strategy_id", sa.String(length=64), nullable=True))
    op.add_column("strategy_versions", sa.Column("version", sa.String(length=64), nullable=True))
    op.add_column("strategy_versions", sa.Column("temperature", sa.Float(), nullable=True))
    op.add_column("strategy_versions", sa.Column("prompt_version_id", sa.String(length=64), nullable=True))
    op.add_column("strategy_versions", sa.Column("tool_schema_version_id", sa.String(length=64), nullable=True))
    op.add_column(
        "strategy_versions",
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
    )
    op.create_index("ix_strategy_versions_strategy_id", "strategy_versions", ["strategy_id"])
    op.create_index("ix_strategy_versions_prompt_version_id", "strategy_versions", ["prompt_version_id"])
    op.create_index("ix_strategy_versions_tool_schema_version_id", "strategy_versions", ["tool_schema_version_id"])
    op.create_foreign_key(
        "strategy_versions_strategy_id_fkey",
        "strategy_versions",
        "strategies",
        ["strategy_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "strategy_versions_prompt_version_id_fkey",
        "strategy_versions",
        "prompt_versions",
        ["prompt_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "strategy_versions_tool_schema_version_id_fkey",
        "strategy_versions",
        "tool_schema_versions",
        ["tool_schema_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "test_runs_runtime_profile_id_fkey",
        "test_runs",
        "runtime_profiles",
        ["runtime_profile_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("test_runs_runtime_profile_id_fkey", "test_runs", type_="foreignkey")
    op.drop_constraint("strategy_versions_tool_schema_version_id_fkey", "strategy_versions", type_="foreignkey")
    op.drop_constraint("strategy_versions_prompt_version_id_fkey", "strategy_versions", type_="foreignkey")
    op.drop_constraint("strategy_versions_strategy_id_fkey", "strategy_versions", type_="foreignkey")
    op.drop_index("ix_strategy_versions_tool_schema_version_id", table_name="strategy_versions")
    op.drop_index("ix_strategy_versions_prompt_version_id", table_name="strategy_versions")
    op.drop_index("ix_strategy_versions_strategy_id", table_name="strategy_versions")
    op.drop_column("strategy_versions", "is_locked")
    op.drop_column("strategy_versions", "tool_schema_version_id")
    op.drop_column("strategy_versions", "prompt_version_id")
    op.drop_column("strategy_versions", "temperature")
    op.drop_column("strategy_versions", "version")
    op.drop_column("strategy_versions", "strategy_id")

    op.drop_table("tool_schema_versions")
    op.drop_table("prompt_versions")
    op.drop_table("strategies")
    op.drop_index("idx_runtime_profiles_project_id", table_name="runtime_profiles")
    op.drop_table("runtime_profiles")
