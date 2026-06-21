from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RuntimeProfile(Base):
    __tablename__ = "runtime_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    executor: Mapped[str] = mapped_column(String(32), nullable=False, default="local_subprocess")
    image: Mapped[str | None] = mapped_column(String(255))
    working_dir: Mapped[str | None] = mapped_column(String(255))
    python_version: Mapped[str | None] = mapped_column(String(64))
    install_command: Mapped[str | None] = mapped_column(Text())
    test_command: Mapped[str] = mapped_column(Text(), nullable=False)
    env_template: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    resource_limits: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    replay_policy: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    network_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="default")
    artifact_policy: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    cleanup_policy: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
