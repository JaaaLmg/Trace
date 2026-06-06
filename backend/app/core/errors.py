# 错误码：对齐 系统设计.md §12.2，评测和状态机都按这个分类
from enum import Enum


class ErrorCode(str, Enum):
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"
    TOOL_ARGUMENT_ERROR = "TOOL_ARGUMENT_ERROR"
    PROJECT_ANALYSIS_FAILED = "PROJECT_ANALYSIS_FAILED"
    DEPENDENCY_INSTALL_FAILED = "DEPENDENCY_INSTALL_FAILED"
    PYTEST_COLLECTION_FAILED = "PYTEST_COLLECTION_FAILED"
    PYTEST_EXECUTION_FAILED = "PYTEST_EXECUTION_FAILED"
    RUNNER_TIMEOUT = "RUNNER_TIMEOUT"
    RUNNER_INTERNAL_ERROR = "RUNNER_INTERNAL_ERROR"
    REFLECTION_CONTRACT_VIOLATION = "REFLECTION_CONTRACT_VIOLATION"
    ARTIFACT_UPLOAD_FAILED = "ARTIFACT_UPLOAD_FAILED"


class TraceError(Exception):
    """带错误码的领域异常。阶段失败时：先落 run_events + trace_steps，再抛它。

    details 选填：失败现场的结构化上下文（如结构化输出失败时的 attempt_logs），供上层落 trace。
    """

    def __init__(self, code: ErrorCode, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
