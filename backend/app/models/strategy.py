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

    # 策略版本主键，例如 sv-direct-v1。
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # 展示名称，如 Direct v1 / ReAct Reflection v1。
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 工作流类型，决定 orchestrator 走 direct / plan_execute / react_reflection 哪条分支。
    workflow_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # 默认模型提供商。V1 本地验证多使用 mock。
    model_provider: Mapped[str] = mapped_column(String(64), nullable=False, default="mock")
    # 默认模型名称。
    model_name: Mapped[str] = mapped_column(String(255), nullable=False, default="mock-1")
    # 额外模型参数，便于后续接真实 LLM 时保存 temperature / top_p 等。
    model_params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 是否允许一次 reflection。
    allow_reflection: Mapped[bool] = mapped_column(nullable=False, default=False)
    # 最大工具调用次数预算。
    max_tool_calls: Mapped[int] = mapped_column(nullable=False, default=12)
    # prompt 模板引用版本。V1 只保存引用，不展开完整 prompt 表。
    prompt_ref: Mapped[str] = mapped_column(String(128), nullable=False, default="v1")
    # 工具 schema 引用版本。
    tool_schema_ref: Mapped[str] = mapped_column(String(128), nullable=False, default="v1")
    # 创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
