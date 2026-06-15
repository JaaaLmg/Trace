from app.db.base import Base
from app.models import load_all_models


def test_v1_metadata_registers_14_tables():
    load_all_models()
    names = set(Base.metadata.tables)
    # V1 的 14 张表必须始终在册；V2 在其上扩展（runtime_profiles/strategies/
    # prompt_versions/tool_schema_versions 等），所以这里用子集校验而非全等，
    # 否则每加一张 V2 表都要回来改这个守卫。
    v1_tables = {
        "projects",
        "project_snapshots",
        "strategy_versions",
        "test_plans",
        "test_runs",
        "run_plan_items",
        "run_attempts",
        "generated_test_files",
        "generated_test_cases",
        "pytest_case_results",
        "trace_steps",
        "run_events",
        "run_artifacts",
        "test_reports",
    }
    assert v1_tables <= names
