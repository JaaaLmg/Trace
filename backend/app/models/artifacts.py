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

    # 生成测试文件版本主键。
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # 所属 attempt。
    attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("run_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 写入到项目中的相对路径。
    path: Mapped[str] = mapped_column(Text(), nullable=False)
    # 文件全文。V1 为了查询方便直接入库。
    content_text: Mapped[str | None] = mapped_column(Text())
    # 文件内容哈希，用于判重或后续 diff。
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    # 若文件大到需要转 artifact，可引用外部产物；V1 可空。
    artifact_id: Mapped[str | None] = mapped_column(String(36))
    # 若这是修复后的版本，可指向前一版文件。
    previous_file_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("generated_test_files.id", ondelete="SET NULL")
    )
    # 预留 diff 产物引用。
    diff_artifact_id: Mapped[str | None] = mapped_column(String(36))
    # 生成原因，例如 initial generation / reflection fix。
    generation_reason: Mapped[str | None] = mapped_column(Text())
    # 创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class GeneratedTestCase(Base):
    __tablename__ = "generated_test_cases"

    # 生成用例主键。
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # 所属生成文件。
    file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("generated_test_files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # pytest nodeid，若成功映射则用于和运行结果对齐。
    nodeid: Mapped[str | None] = mapped_column(Text())
    # 测试函数名。
    test_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 在源文件中的起始行。
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    # 在源文件中的结束行。
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    # 若用例针对具体路由，可记录路由信息。
    target_route: Mapped[str | None] = mapped_column(Text())
    # 若用例针对具体函数，可记录函数名。
    target_function: Mapped[str | None] = mapped_column(Text())
    # 断言摘要，方便前端概览展示。
    assertion_summary: Mapped[str | None] = mapped_column(Text())
    # 生成该用例的策略版本。
    source_strategy_version_id: Mapped[str | None] = mapped_column(String(64))
    # 人工采纳状态，供后续人机协作使用。
    adoption_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    # 人工打分，衡量用例有意义程度。
    human_meaningfulness_score: Mapped[int | None] = mapped_column(Integer)
    # 规则命中标记，给质量分析使用。
    rule_flags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)


class PytestCaseResult(Base):
    __tablename__ = "pytest_case_results"

    # pytest 单用例结果主键。
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # 所属 attempt。
    attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("run_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 若能映射回 generated_test_cases，则写其主键。
    generated_test_case_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("generated_test_cases.id", ondelete="SET NULL"), index=True
    )
    # pytest nodeid。
    nodeid: Mapped[str] = mapped_column(Text(), nullable=False, index=True)
    # 映射状态，说明 nodeid 是否成功对上生成用例。
    mapping_status: Mapped[str] = mapped_column(String(32), nullable=False, default="matched")
    # 用例状态：passed/failed/error/skipped。
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    # 用例耗时，单位毫秒。
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 失败类型，如 assertion / import / collection。
    failure_type: Mapped[str | None] = mapped_column(String(32))
    # 失败摘要。
    failure_message: Mapped[str | None] = mapped_column(Text())
    # traceback 哈希，便于去重。
    traceback_hash: Mapped[str | None] = mapped_column(String(128))
    # 标准输出摘要，V1 先预留。
    stdout_excerpt: Mapped[str | None] = mapped_column(Text())
    # 标准错误摘要，V1 先预留。
    stderr_excerpt: Mapped[str | None] = mapped_column(Text())
    # 是否是收集阶段错误。注意这类记录不计入 collected。
    is_collection_error: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RunArtifact(Base):
    __tablename__ = "run_artifacts"

    # 通用产物主键。
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # 所属 run。
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 可选所属 attempt，用于区分某一轮生成出来的局部产物。
    attempt_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("run_attempts.id", ondelete="SET NULL"), index=True
    )
    # 远程执行场景下可关联 runner job；V1 本地执行通常为空。
    runner_job_id: Mapped[str | None] = mapped_column(String(36))
    # 产物类型，如 report_md、report_json。
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # 产物 URI。V1 通常直接存本地文件路径。
    uri: Mapped[str] = mapped_column(Text(), nullable=False)
    # 内容哈希。
    content_hash: Mapped[str | None] = mapped_column(String(128))
    # 文件大小。
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    # 产物附加元数据。
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    # 创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class TestReport(Base):
    __tablename__ = "test_reports"

    # 报告主键。
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # 所属 run，且一条 run 只对应一份最终报告。
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    # 报告摘要，给列表页快速展示。
    summary: Mapped[str] = mapped_column(Text(), nullable=False)
    # 结构化指标，是前端展示和筛选的核心来源。
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 风险提示文本。
    risk_notes: Mapped[str | None] = mapped_column(Text())
    # 预留 markdown artifact 外键。
    markdown_artifact_id: Mapped[str | None] = mapped_column(String(36))
    # 预留 json artifact 外键。
    json_artifact_id: Mapped[str | None] = mapped_column(String(36))
    # markdown 报告文件路径。
    markdown_uri: Mapped[str | None] = mapped_column(Text())
    # json 报告文件路径。
    json_uri: Mapped[str | None] = mapped_column(Text())
    # 创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
