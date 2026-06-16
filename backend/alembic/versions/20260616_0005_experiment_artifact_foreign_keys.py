"""add experiment artifact foreign keys

Revision ID: 20260616_0005
Revises: 20260615_0004
Create Date: 2026-06-16
"""
from __future__ import annotations

from alembic import op

revision = "20260616_0005"
down_revision = "20260615_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_experiment_clean_runs_generated_test_set_artifact_id",
        "experiment_clean_runs",
        "run_artifacts",
        ["generated_test_set_artifact_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_test_replays_generated_test_set_artifact_id",
        "test_replays",
        "run_artifacts",
        ["generated_test_set_artifact_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_test_replays_generated_test_set_artifact_id",
        "test_replays",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_experiment_clean_runs_generated_test_set_artifact_id",
        "experiment_clean_runs",
        type_="foreignkey",
    )
