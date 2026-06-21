"""v23 runtime bindings and replay policy

Revision ID: 20260621_0008
Revises: 20260620_0007
Create Date: 2026-06-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260621_0008"
down_revision = "20260620_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {
        table: {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
        for table in ("runtime_profiles", "experiments")
    }
    if "replay_policy" not in existing["runtime_profiles"]:
        op.add_column(
            "runtime_profiles",
            sa.Column("replay_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        )
    if "runtime_profile_bindings" not in existing["experiments"]:
        op.add_column(
            "experiments",
            sa.Column("runtime_profile_bindings", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        )
    if "experiment_lifecycle_events" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "experiment_lifecycle_events",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("experiment_id", sa.String(length=64), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("scope", sa.String(length=64), nullable=False),
            sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_experiment_lifecycle_events_experiment_id"),
            "experiment_lifecycle_events",
            ["experiment_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_experiment_lifecycle_events_event_type"),
            "experiment_lifecycle_events",
            ["event_type"],
            unique=False,
        )


def downgrade() -> None:
    existing = {
        table: {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
        for table in ("runtime_profiles", "experiments")
    }
    if "experiment_lifecycle_events" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_index(op.f("ix_experiment_lifecycle_events_event_type"), table_name="experiment_lifecycle_events")
        op.drop_index(op.f("ix_experiment_lifecycle_events_experiment_id"), table_name="experiment_lifecycle_events")
        op.drop_table("experiment_lifecycle_events")
    if "runtime_profile_bindings" in existing["experiments"]:
        op.drop_column("experiments", "runtime_profile_bindings")
    if "replay_policy" in existing["runtime_profiles"]:
        op.drop_column("runtime_profiles", "replay_policy")
