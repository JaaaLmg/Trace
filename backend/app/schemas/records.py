# 持久化记录体：对齐 系统设计.md §9.2 的表字段子集（V1 简化版）。
# 这些是 A 产出、经 RunRecorder 端口落库的数据形状；B 接 SQLAlchemy 时字段一一对应。
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.core.ids import new_id
from app.schemas.trace import RunStatus, Stage

AttemptKind = Literal["initial", "reflection"]
AttemptStatus = Literal["running", "passed", "failed", "error"]
PlanItemStatus = Literal["pending", "generating", "executing", "done", "failed"]
MappingStatus = Literal["matched", "unmatched"]
AdoptionStatus = Literal["pending", "adopted", "rejected"]


class TestRunRecord(BaseModel):
    __test__ = False  # 不是 pytest 测试类：名字撞上 Test* 收集启发式
    id: str = Field(default_factory=new_id)
    test_plan_id: Optional[str] = None
    retry_of_run_id: Optional[str] = None
    project_snapshot_id: Optional[str] = None
    runtime_profile_id: Optional[str] = None  # V1 恒为 None，环境写进 runtime_snapshot
    strategy_version_id: str
    runtime_snapshot: dict = Field(default_factory=dict)
    strategy_snapshot: dict = Field(default_factory=dict)  # 冻结 prompt 正文 + 模型参数
    status: RunStatus = "queued"
    stage: Optional[Stage] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    total_tokens: int = 0
    tool_call_count: int = 0
    pytest_summary: dict = Field(default_factory=dict)
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class RunPlanItemRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    run_id: str
    index: int
    target_type: str
    target_ref: str
    goal: str
    planned_assertions: list[str] = Field(default_factory=list)
    status: PlanItemStatus = "pending"


class RunAttemptRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    run_plan_item_id: str
    attempt_no: int
    kind: AttemptKind
    status: AttemptStatus = "running"
    pytest_exit_code: Optional[int] = None
    error_code: Optional[str] = None
    reflection_reason: Optional[str] = None


class GeneratedTestFileRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    attempt_id: str
    path: str
    content_text: Optional[str] = None  # V1 文件小，直接存库
    content_hash: str
    previous_file_id: Optional[str] = None  # reflection 修复后指向上一版
    generation_reason: Optional[str] = None


class GeneratedTestCaseRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    file_id: str
    nodeid: Optional[str] = None
    test_name: str
    start_line: int
    end_line: int
    target_route: Optional[str] = None
    target_function: Optional[str] = None
    assertion_summary: Optional[str] = None
    source_strategy_version_id: Optional[str] = None
    adoption_status: AdoptionStatus = "pending"
    human_meaningfulness_score: Optional[int] = None  # 评测时人工回填
    rule_flags: list[str] = Field(default_factory=list)


class PytestCaseResultRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    attempt_id: str
    generated_test_case_id: Optional[str] = None  # 对不上时为空 + mapping_status=unmatched
    nodeid: str
    mapping_status: MappingStatus = "matched"
    status: str
    duration_ms: int = 0
    failure_type: Optional[str] = None
    failure_message: Optional[str] = None
    traceback_hash: Optional[str] = None
    is_collection_error: bool = False  # 收集期错误的伪记录：报告汇总 collected 时要摘出去


class RunArtifactRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    run_id: str
    attempt_id: Optional[str] = None
    artifact_type: str
    uri: str  # V1 存本地文件系统路径
    content_hash: Optional[str] = None
    size_bytes: Optional[int] = None
    metadata: dict = Field(default_factory=dict)


class TestReportRecord(BaseModel):
    __test__ = False  # 同上，避免被 pytest 误收集
    id: str = Field(default_factory=new_id)
    run_id: str
    summary: str
    metrics: dict = Field(default_factory=dict)
    risk_notes: Optional[str] = None
    markdown_uri: Optional[str] = None
    json_uri: Optional[str] = None
