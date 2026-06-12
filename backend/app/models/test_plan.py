from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TestPlan(Base):
    __tablename__ = "test_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_scope: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    goal: Mapped[str] = mapped_column(Text(), nullable=False)
    budget: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output_options: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    default_strategy_version_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("strategy_versions.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
