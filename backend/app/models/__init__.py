from app.models.artifacts import GeneratedTestCase, GeneratedTestFile, PytestCaseResult, RunArtifact, TestReport
from app.models.project import Project, ProjectSnapshot
from app.models.runtime_profile import RuntimeProfile
from app.models.strategy import StrategyVersion
from app.models.test_plan import TestPlan
from app.models.test_run import RunAttempt, RunPlanItem, TestRun
from app.models.trace import RunEvent, TraceStep
from app.models.versioning import PromptVersion, Strategy, ToolSchemaVersion

__all__ = [
    "Project",
    "ProjectSnapshot",
    "RuntimeProfile",
    "Strategy",
    "StrategyVersion",
    "PromptVersion",
    "ToolSchemaVersion",
    "TestPlan",
    "TestRun",
    "RunPlanItem",
    "RunAttempt",
    "GeneratedTestFile",
    "GeneratedTestCase",
    "PytestCaseResult",
    "TraceStep",
    "RunEvent",
    "RunArtifact",
    "TestReport",
    "load_all_models",
]


def load_all_models() -> None:
    # 导入副作用：让 SQLAlchemy metadata 注册完整 14 张表
    return None
