from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TraceStep(Base):
    __tablename__ = "trace_steps"
    __table_args__ = (UniqueConstraint("run_id", "step_index", name="uq_trace_steps_run_id_step_index"),)

    # trace 步骤主键。
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # 所属 run。
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 若该步骤属于某一轮 attempt，则记录 attempt_id。
    attempt_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("run_attempts.id", ondelete="SET NULL"), index=True
    )
    # 步骤顺序号，是前端时间线的排序主键。
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # 步骤类型，如 planning/generation/tool/report。
    step_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # 步骤显示名。
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 输入摘要，给列表页快速预览。
    input_summary: Mapped[str | None] = mapped_column(Text())
    # 输出摘要，给列表页快速预览。
    output_summary: Mapped[str | None] = mapped_column(Text())
    # 若这是工具调用相关步骤，记录工具名。
    tool_name: Mapped[str | None] = mapped_column(String(128))
    # 结构化详情载荷，详情抽屉主要看这里。
    payload: Mapped[dict | None] = mapped_column(JSONB)
    # token 消耗。
    tokens: Mapped[int | None] = mapped_column(Integer)
    # 步骤耗时，单位毫秒。
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    # 步骤状态。
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    # 错误描述。
    error: Mapped[str | None] = mapped_column(Text())
    # 创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class RunEvent(Base):
    __tablename__ = "run_events"

    # 事件主键。
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # 所属 run。
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 所属阶段，可为空。
    stage: Mapped[str | None] = mapped_column(String(32), index=True)
    # 事件类型，如 run_enqueued、stage_enter、run_finish。
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # 事件发生前状态。
    status_before: Mapped[str | None] = mapped_column(String(32))
    # 事件发生后状态。
    status_after: Mapped[str | None] = mapped_column(String(32))
    # 事件描述。
    message: Mapped[str | None] = mapped_column(Text())
    # 创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
