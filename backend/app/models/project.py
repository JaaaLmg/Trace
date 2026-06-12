from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    # 项目主键，所有计划/快照都从这里出发。
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # 项目显示名，给前端列表和详情页直接展示。
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # 业务描述，可为空，帮助人理解被测项目用途。
    description: Mapped[str | None] = mapped_column(Text())
    # 项目来源类型。V1 固定是 local_path，后续才可能扩展 git/repo。
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="local_path")
    # 远程仓库地址，V1 可空。
    repo_url: Mapped[str | None] = mapped_column(Text())
    # 本地项目根目录，后续创建 snapshot 默认从这里复制。
    local_path: Mapped[str] = mapped_column(Text(), nullable=False)
    # 默认分支名，V1 只是预留，不参与实际执行。
    default_branch: Mapped[str | None] = mapped_column(String(255))
    # 项目主要语言，给后续展示和扩展使用。
    language: Mapped[str] = mapped_column(String(64), nullable=False, default="python")
    # 项目框架类型，当前仓库主要面向 fastapi。
    framework: Mapped[str] = mapped_column(String(64), nullable=False, default="fastapi")
    # 项目状态，V1 简化为 active 等少量枚举。
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    # 创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    # 最后更新时间，项目编辑时自动刷新。
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class ProjectSnapshot(Base):
    __tablename__ = "project_snapshots"

    # 快照主键，一次 run 必须绑定一个 snapshot，而不是直接裸跑项目。
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # 所属项目。
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 快照来源类型。V1 里通常和项目一样，也是 local_path。
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    # 此次执行真正使用的代码根目录。
    root_path: Mapped[str] = mapped_column(Text(), nullable=False)
    # 可选内容哈希，未来可用于区分不同代码状态；V1 可空。
    content_hash: Mapped[str | None] = mapped_column(String(128))
    # 快照创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
