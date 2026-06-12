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

    # 测试计划主键，描述“要如何测”，而不是一次执行本身。
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # 所属项目。
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 计划名称，给前端展示与区分不同测试目标。
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 测试目标范围，如模块、路由、函数名等；V1 直接用 JSON 数组保存。
    target_scope: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # 人类输入的目标描述，例如“覆盖订单价格计算逻辑”。
    goal: Mapped[str] = mapped_column(Text(), nullable=False)
    # 执行预算，如 timeout_seconds、allow_reflection 等。
    budget: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 输出偏好，V1 先预留为 JSON。
    output_options: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 默认策略版本。用户在创建 run 时若不显式传策略，就回落到这里。
    default_strategy_version_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("strategy_versions.id", ondelete="SET NULL")
    )
    # 计划状态。
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    # 创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    # 最后更新时间。
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
