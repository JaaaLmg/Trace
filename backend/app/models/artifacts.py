from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GeneratedTestFile(Base):
    __tablename__ = "generated_test_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("run_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    path: Mapped[str] = mapped_column(Text(), nullable=False)
    content_text: Mapped[str | None] = mapped_column(Text())
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_id: Mapped[str | None] = mapped_column(String(36))
    previous_file_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("generated_test_files.id", ondelete="SET NULL")
    )
    diff_artifact_id: Mapped[str | None] = mapped_column(String(36))
    generation_reason: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class GeneratedTestCase(Base):
    __tablename__ = "generated_test_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("generated_test_files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nodeid: Mapped[str | None] = mapped_column(Text())
    test_name: Mapped[str] = mapped_column(String(255), nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    target_route: Mapped[str | None] = mapped_column(Text())
    target_function: Mapped[str | None] = mapped_column(Text())
    assertion_summary: Mapped[str | None] = mapped_column(Text())
    source_strategy_version_id: Mapped[str | None] = mapped_column(String(64))
    adoption_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    human_meaningfulness_score: Mapped[int | None] = mapped_column(Integer)
    rule_flags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)


class PytestCaseResult(Base):
    __tablename__ = "pytest_case_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("run_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    generated_test_case_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("generated_test_cases.id", ondelete="SET NULL"), index=True
    )
    nodeid: Mapped[str] = mapped_column(Text(), nullable=False, index=True)
    mapping_status: Mapped[str] = mapped_column(String(32), nullable=False, default="matched")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_type: Mapped[str | None] = mapped_column(String(32))
    failure_message: Mapped[str | None] = mapped_column(Text())
    traceback_hash: Mapped[str | None] = mapped_column(String(128))
    stdout_excerpt: Mapped[str | None] = mapped_column(Text())
    stderr_excerpt: Mapped[str | None] = mapped_column(Text())
    is_collection_error: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RunArtifact(Base):
    __tablename__ = "run_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("run_attempts.id", ondelete="SET NULL"), index=True
    )
    runner_job_id: Mapped[str | None] = mapped_column(String(36))
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    uri: Mapped[str] = mapped_column(Text(), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class TestReport(Base):
    __tablename__ = "test_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    summary: Mapped[str] = mapped_column(Text(), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    risk_notes: Mapped[str | None] = mapped_column(Text())
    markdown_artifact_id: Mapped[str | None] = mapped_column(String(36))
    json_artifact_id: Mapped[str | None] = mapped_column(String(36))
    markdown_uri: Mapped[str | None] = mapped_column(Text())
    json_uri: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
