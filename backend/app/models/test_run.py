from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TestRun(Base):
    __tablename__ = "test_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    test_plan_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("test_plans.id", ondelete="SET NULL"), index=True
    )
    retry_of_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("test_runs.id", ondelete="SET NULL"), index=True
    )
    project_snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project_snapshots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    runtime_profile_id: Mapped[str | None] = mapped_column(String(36))
    strategy_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("strategy_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    runtime_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    strategy_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    stage: Mapped[str | None] = mapped_column(String(32), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    total_cost: Mapped[float | None] = mapped_column(Numeric(12, 4))
    tool_call_count: Mapped[int] = mapped_column(nullable=False, default=0)
    pytest_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class RunPlanItem(Base):
    __tablename__ = "run_plan_items"
    __table_args__ = (UniqueConstraint("run_id", "index", name="uq_run_plan_items_run_id_index"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_ref: Mapped[str] = mapped_column(Text(), nullable=False)
    goal: Mapped[str] = mapped_column(Text(), nullable=False)
    planned_assertions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")


class RunAttempt(Base):
    __tablename__ = "run_attempts"
    __table_args__ = (UniqueConstraint("run_plan_item_id", "attempt_no", name="uq_run_attempts_item_attempt"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_plan_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("run_plan_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pytest_exit_code: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(128))
    reflection_reason: Mapped[str | None] = mapped_column(Text())
