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

    # 一次具体执行的主键。
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # 对应的测试计划。V1 的 run 必须来自一个明确 plan，避免孤儿 run 破坏 retry/execute 语义。
    test_plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_plans.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # 若这是一次 retry，则指向原 run。
    retry_of_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("test_runs.id", ondelete="SET NULL"), index=True
    )
    # 运行绑定的项目快照，V1 要求非空。
    project_snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project_snapshots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # 运行环境 profile，V1 暂不单独建表，所以可以为空。
    runtime_profile_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("runtime_profiles.id", ondelete="RESTRICT"), index=True
    )
    # 运行实际采用的策略版本，V1 要求非空。
    strategy_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("strategy_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # 运行时快照，保存模式、环境等信息，避免只依赖外部实时状态。
    runtime_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 策略快照，保存本次运行真正采用的策略参数。
    strategy_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # run 状态，如 queued/running/completed/failed/cancelled。
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    # 当前阶段，供前端展示时间线位置。
    stage: Mapped[str | None] = mapped_column(String(32), index=True)
    # 实际开始执行时间。
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 实际结束执行时间。
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 累计 token 消耗。
    total_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    # 预留的成本字段，当前多数 mock 路径不真正填充。
    total_cost: Mapped[float | None] = mapped_column(Numeric(12, 4))
    # 工具调用次数，用来衡量策略成本。
    tool_call_count: Mapped[int] = mapped_column(nullable=False, default=0)
    # pytest 汇总摘要，给 run 列表和详情页快速显示结果。
    pytest_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 失败错误码。
    error_code: Mapped[str | None] = mapped_column(String(128))
    # 失败错误信息。
    error_message: Mapped[str | None] = mapped_column(Text())
    # 创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class RunPlanItem(Base):
    __tablename__ = "run_plan_items"
    __table_args__ = (UniqueConstraint("run_id", "index", name="uq_run_plan_items_run_id_index"),)

    # 拆分后的单个计划项主键。
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # 所属 run。
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 计划项顺序，用于前端稳定展示和 attempt 归属。
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    # 目标类型，如 goal/function/route。
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # 目标引用值，如具体函数名或“all”。
    target_ref: Mapped[str] = mapped_column(Text(), nullable=False)
    # 当前计划项要达成的目标。
    goal: Mapped[str] = mapped_column(Text(), nullable=False)
    # 计划阶段预期要验证的断言列表。
    planned_assertions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # 当前计划项状态。
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")


class RunAttempt(Base):
    __tablename__ = "run_attempts"
    __table_args__ = (UniqueConstraint("run_plan_item_id", "attempt_no", name="uq_run_attempts_item_attempt"),)

    # 某个计划项的一次具体尝试主键。
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # 所属计划项。
    run_plan_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("run_plan_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 尝试序号，通常 1 是 initial，2 可能是 reflection。
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    # 尝试类型，区分 initial 和 reflection。
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # 尝试状态。
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    # 尝试开始时间。
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 尝试结束时间。
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # pytest 进程退出码。
    pytest_exit_code: Mapped[int | None] = mapped_column(Integer)
    # 尝试级错误码，例如 reflection contract violation。
    error_code: Mapped[str | None] = mapped_column(String(128))
    # 若是 reflection，此处记录本轮反思原因。
    reflection_reason: Mapped[str | None] = mapped_column(Text())
