from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    workflow_type: Mapped[str] = mapped_column(String(64), nullable=False)
    model_provider: Mapped[str] = mapped_column(String(64), nullable=False, default="mock")
    model_name: Mapped[str] = mapped_column(String(255), nullable=False, default="mock-1")
    model_params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    allow_reflection: Mapped[bool] = mapped_column(nullable=False, default=False)
    max_tool_calls: Mapped[int] = mapped_column(nullable=False, default=12)
    prompt_ref: Mapped[str] = mapped_column(String(128), nullable=False, default="v1")
    tool_schema_ref: Mapped[str] = mapped_column(String(128), nullable=False, default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
