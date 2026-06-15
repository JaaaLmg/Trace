from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"

    # 策略版本主键，例如 sv-direct-v1。
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # 策略逻辑父表，例如 direct / react_reflection。
    strategy_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("strategies.id", ondelete="RESTRICT"), index=True
    )
    # 展示名称，如 Direct v1 / ReAct Reflection v1。
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 版本号，如 v1 / v2。
    version: Mapped[str | None] = mapped_column(String(64))
    # 工作流类型，决定 orchestrator 走 direct / plan_execute / react_reflection 哪条分支。
    workflow_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # 默认模型提供商。V1 本地验证多使用 mock。
    model_provider: Mapped[str] = mapped_column(String(64), nullable=False, default="mock")
    # 默认模型名称。
    model_name: Mapped[str] = mapped_column(String(255), nullable=False, default="mock-1")
    # 额外模型参数，便于后续接真实 LLM 时保存 temperature / top_p 等。
    model_params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 默认温度字段；其余模型参数仍保留在 model_params 中。
    temperature: Mapped[float | None] = mapped_column(Float)
    # 是否允许一次 reflection。
    allow_reflection: Mapped[bool] = mapped_column(nullable=False, default=False)
    # 最大工具调用次数预算。
    max_tool_calls: Mapped[int] = mapped_column(nullable=False, default=12)
    # 绑定的 prompt 正文版本。
    prompt_version_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("prompt_versions.id", ondelete="RESTRICT"), index=True
    )
    # 绑定的工具 schema 正文版本。
    tool_schema_version_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("tool_schema_versions.id", ondelete="RESTRICT"), index=True
    )
    # prompt 模板引用版本。V1 只保存引用，不展开完整 prompt 表。
    prompt_ref: Mapped[str] = mapped_column(String(128), nullable=False, default="v1")
    # 工具 schema 引用版本。
    tool_schema_ref: Mapped[str] = mapped_column(String(128), nullable=False, default="v1")
    # 被 run 引用后视为锁定，不允许原地改历史语义。
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
