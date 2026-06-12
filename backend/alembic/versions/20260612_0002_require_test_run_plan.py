"""require test_runs.test_plan_id

Revision ID: 20260612_0002
Revises: 20260612_0001
Create Date: 2026-06-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260612_0002"
down_revision = "20260612_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO test_plans (
                id,
                project_id,
                name,
                target_scope,
                goal,
                budget,
                output_options,
                status,
                created_at,
                updated_at
            )
            SELECT
                'mig-plan-' || substr(md5(snapshots.project_id), 1, 27),
                snapshots.project_id,
                'Recovered orphan runs',
                '[]'::jsonb,
                'Recovered orphan runs during schema migration.',
                '{}'::jsonb,
                '{}'::jsonb,
                'archived',
                NOW(),
                NOW()
            FROM test_runs runs
            JOIN project_snapshots snapshots ON snapshots.id = runs.project_snapshot_id
            WHERE runs.test_plan_id IS NULL
            GROUP BY snapshots.project_id
            ON CONFLICT (id) DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE test_runs runs
            SET test_plan_id = 'mig-plan-' || substr(md5(snapshots.project_id), 1, 27)
            FROM project_snapshots snapshots
            WHERE snapshots.id = runs.project_snapshot_id
              AND runs.test_plan_id IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM test_runs
                    WHERE test_plan_id IS NULL
                ) THEN
                    RAISE EXCEPTION 'test_runs.test_plan_id still contains NULL rows after migration backfill';
                END IF;
            END $$;
            """
        )
    )

    op.drop_constraint("test_runs_test_plan_id_fkey", "test_runs", type_="foreignkey")
    op.alter_column("test_runs", "test_plan_id", existing_type=sa.String(length=36), nullable=False)
    op.create_foreign_key(
        "test_runs_test_plan_id_fkey",
        "test_runs",
        "test_plans",
        ["test_plan_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("test_runs_test_plan_id_fkey", "test_runs", type_="foreignkey")
    op.alter_column("test_runs", "test_plan_id", existing_type=sa.String(length=36), nullable=True)
    op.create_foreign_key(
        "test_runs_test_plan_id_fkey",
        "test_runs",
        "test_plans",
        ["test_plan_id"],
        ["id"],
        ondelete="SET NULL",
    )
