"""stage3 evaluation and experiment tables

Revision ID: 20260615_0004
Revises: 20260615_0003
Create Date: 2026-06-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260615_0004"
down_revision = "20260615_0003"
branch_labels = None
depends_on = None


def _jsonb_default(value: str = "{}") -> sa.TextClause:
    return sa.text(f"'{value}'::jsonb")


def upgrade() -> None:
    op.create_table(
        "eval_datasets",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("project_snapshot_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default("[]")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("name", "version", name="uq_eval_datasets_name_version"),
    )

    op.create_table(
        "eval_tasks",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("dataset_id", sa.String(length=64), sa.ForeignKey("eval_datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_snapshot_id", sa.String(length=36), sa.ForeignKey("project_snapshots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default()),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("expected_capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default("[]")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_eval_tasks_dataset_id", "eval_tasks", ["dataset_id"])
    op.create_index("ix_eval_tasks_project_snapshot_id", "eval_tasks", ["project_snapshot_id"])

    op.create_table(
        "seeded_bugs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("eval_task_id", sa.String(length=64), sa.ForeignKey("eval_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bug_type", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("expected_detection", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_seeded_bugs_eval_task_id", "seeded_bugs", ["eval_task_id"])

    op.create_table(
        "bug_variants",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("seeded_bug_id", sa.String(length=64), sa.ForeignKey("seeded_bugs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_name", sa.String(length=255), nullable=False),
        sa.Column("canonical_kind", sa.String(length=32), nullable=False, server_default="patch"),
        sa.Column("patch_artifact_id", sa.String(length=64), nullable=True),
        sa.Column("mutated_snapshot_id", sa.String(length=36), sa.ForeignKey("project_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ground_truth", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_bug_variants_seeded_bug_id", "bug_variants", ["seeded_bug_id"])
    op.create_index("ix_bug_variants_mutated_snapshot_id", "bug_variants", ["mutated_snapshot_id"])

    op.create_table(
        "experiments",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), sa.ForeignKey("eval_datasets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("repeat_count", sa.Integer(), nullable=False),
        sa.Column("llm_override", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_experiments_dataset_id", "experiments", ["dataset_id"])
    op.create_index("ix_experiments_status", "experiments", ["status"])

    op.create_table(
        "experiment_strategy_versions",
        sa.Column("experiment_id", sa.String(length=64), sa.ForeignKey("experiments.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("strategy_version_id", sa.String(length=64), sa.ForeignKey("strategy_versions.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    op.create_table(
        "experiment_clean_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("experiment_id", sa.String(length=64), sa.ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("eval_task_id", sa.String(length=64), sa.ForeignKey("eval_tasks.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("strategy_version_id", sa.String(length=64), sa.ForeignKey("strategy_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("repeat_index", sa.Integer(), nullable=False),
        sa.Column("clean_run_id", sa.String(length=36), sa.ForeignKey("test_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generated_test_set_artifact_id", sa.String(length=64), nullable=False),
        sa.Column("false_positive", sa.Boolean(), nullable=False),
        sa.Column("clean_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint(
            "experiment_id",
            "eval_task_id",
            "strategy_version_id",
            "repeat_index",
            name="uq_experiment_clean_runs_unit",
        ),
    )
    op.create_index("ix_experiment_clean_runs_experiment_id", "experiment_clean_runs", ["experiment_id"])
    op.create_index("ix_experiment_clean_runs_eval_task_id", "experiment_clean_runs", ["eval_task_id"])
    op.create_index("ix_experiment_clean_runs_strategy_version_id", "experiment_clean_runs", ["strategy_version_id"])
    op.create_index("ix_experiment_clean_runs_clean_run_id", "experiment_clean_runs", ["clean_run_id"])

    op.create_table(
        "test_replays",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("experiment_clean_run_id", sa.String(length=36), sa.ForeignKey("experiment_clean_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("generated_test_set_artifact_id", sa.String(length=64), nullable=False),
        sa.Column("target_snapshot_id", sa.String(length=36), sa.ForeignKey("project_snapshots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("bug_variant_id", sa.String(length=64), sa.ForeignKey("bug_variants.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("pytest_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default()),
        sa.Column("replay_mode", sa.String(length=32), nullable=False, server_default="frozen_test_set"),
        sa.Column("llm_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_test_replays_experiment_clean_run_id", "test_replays", ["experiment_clean_run_id"])
    op.create_index("ix_test_replays_target_snapshot_id", "test_replays", ["target_snapshot_id"])
    op.create_index("ix_test_replays_bug_variant_id", "test_replays", ["bug_variant_id"])
    op.create_index("ix_test_replays_status", "test_replays", ["status"])

    op.create_table(
        "experiment_replay_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("experiment_clean_run_id", sa.String(length=36), sa.ForeignKey("experiment_clean_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bug_variant_id", sa.String(length=64), sa.ForeignKey("bug_variants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("replay_id", sa.String(length=36), sa.ForeignKey("test_replays.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("captured_bug", sa.Boolean(), nullable=False),
        sa.Column("replay_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("experiment_clean_run_id", "bug_variant_id", name="uq_experiment_replay_runs_bug"),
    )
    op.create_index("ix_experiment_replay_runs_experiment_clean_run_id", "experiment_replay_runs", ["experiment_clean_run_id"])
    op.create_index("ix_experiment_replay_runs_bug_variant_id", "experiment_replay_runs", ["bug_variant_id"])
    op.create_index("ix_experiment_replay_runs_replay_id", "experiment_replay_runs", ["replay_id"])


def downgrade() -> None:
    op.drop_index("ix_experiment_replay_runs_replay_id", table_name="experiment_replay_runs")
    op.drop_index("ix_experiment_replay_runs_bug_variant_id", table_name="experiment_replay_runs")
    op.drop_index("ix_experiment_replay_runs_experiment_clean_run_id", table_name="experiment_replay_runs")
    op.drop_table("experiment_replay_runs")

    op.drop_index("ix_test_replays_status", table_name="test_replays")
    op.drop_index("ix_test_replays_bug_variant_id", table_name="test_replays")
    op.drop_index("ix_test_replays_target_snapshot_id", table_name="test_replays")
    op.drop_index("ix_test_replays_experiment_clean_run_id", table_name="test_replays")
    op.drop_table("test_replays")

    op.drop_index("ix_experiment_clean_runs_clean_run_id", table_name="experiment_clean_runs")
    op.drop_index("ix_experiment_clean_runs_strategy_version_id", table_name="experiment_clean_runs")
    op.drop_index("ix_experiment_clean_runs_eval_task_id", table_name="experiment_clean_runs")
    op.drop_index("ix_experiment_clean_runs_experiment_id", table_name="experiment_clean_runs")
    op.drop_table("experiment_clean_runs")

    op.drop_table("experiment_strategy_versions")

    op.drop_index("ix_experiments_status", table_name="experiments")
    op.drop_index("ix_experiments_dataset_id", table_name="experiments")
    op.drop_table("experiments")

    op.drop_index("ix_bug_variants_mutated_snapshot_id", table_name="bug_variants")
    op.drop_index("ix_bug_variants_seeded_bug_id", table_name="bug_variants")
    op.drop_table("bug_variants")

    op.drop_index("ix_seeded_bugs_eval_task_id", table_name="seeded_bugs")
    op.drop_table("seeded_bugs")

    op.drop_index("ix_eval_tasks_project_snapshot_id", table_name="eval_tasks")
    op.drop_index("ix_eval_tasks_dataset_id", table_name="eval_tasks")
    op.drop_table("eval_tasks")

    op.drop_table("eval_datasets")
