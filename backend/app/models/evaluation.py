from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvalDataset(Base):
    __tablename__ = "eval_datasets"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_eval_datasets_name_version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text())
    project_snapshot_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class EvalTask(Base):
    __tablename__ = "eval_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("eval_datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project_snapshots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    target_scope: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    goal: Mapped[str] = mapped_column(Text(), nullable=False)
    expected_capabilities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SeededBug(Base):
    __tablename__ = "seeded_bugs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    eval_task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("eval_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bug_type: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    expected_detection: Mapped[str] = mapped_column(Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class BugVariant(Base):
    __tablename__ = "bug_variants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    seeded_bug_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("seeded_bugs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="patch")
    patch_artifact_id: Mapped[str | None] = mapped_column(String(64))
    mutated_snapshot_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("project_snapshots.id", ondelete="SET NULL"), index=True
    )
    ground_truth: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("eval_datasets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    runtime_profile_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("runtime_profiles.id", ondelete="RESTRICT"), index=True
    )
    runtime_profile_bindings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    repeat_count: Mapped[int] = mapped_column(Integer, nullable=False)
    llm_override: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text())


class ExperimentStrategyVersion(Base):
    __tablename__ = "experiment_strategy_versions"

    experiment_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("experiments.id", ondelete="CASCADE"), primary_key=True
    )
    strategy_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("strategy_versions.id", ondelete="RESTRICT"), primary_key=True
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ExperimentCleanRun(Base):
    __tablename__ = "experiment_clean_runs"
    __table_args__ = (
        UniqueConstraint(
            "experiment_id",
            "eval_task_id",
            "strategy_version_id",
            "repeat_index",
            name="uq_experiment_clean_runs_unit",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    eval_task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("eval_tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    strategy_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("strategy_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    repeat_index: Mapped[int] = mapped_column(Integer, nullable=False)
    clean_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    generated_test_set_artifact_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("run_artifacts.id", ondelete="RESTRICT"), nullable=False
    )
    false_positive: Mapped[bool] = mapped_column(Boolean, nullable=False)
    clean_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class TestReplay(Base):
    __tablename__ = "test_replays"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    experiment_clean_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("experiment_clean_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    generated_test_set_artifact_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("run_artifacts.id", ondelete="RESTRICT"), nullable=False
    )
    target_snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project_snapshots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    bug_variant_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("bug_variants.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    pytest_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    runtime_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    executor_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    workspace_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    cache_key: Mapped[str | None] = mapped_column(String(128), index=True)
    cache_status: Mapped[str] = mapped_column(String(32), nullable=False, default="miss")
    source_replay_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("test_replays.id", ondelete="SET NULL"))
    replay_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="frozen_test_set")
    llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ExperimentReplayRun(Base):
    __tablename__ = "experiment_replay_runs"
    __table_args__ = (
        UniqueConstraint("experiment_clean_run_id", "bug_variant_id", name="uq_experiment_replay_runs_bug"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    experiment_clean_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("experiment_clean_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bug_variant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("bug_variants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    replay_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_replays.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    captured_bug: Mapped[bool] = mapped_column(Boolean, nullable=False)
    replay_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ExperimentLifecycleEvent(Base):
    __tablename__ = "experiment_lifecycle_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str] = mapped_column(String(64), nullable=False, default="experiment")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
