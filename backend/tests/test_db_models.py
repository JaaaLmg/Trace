from app.db.base import Base
from app.models import load_all_models


def test_v1_metadata_registers_14_tables():
    load_all_models()
    names = set(Base.metadata.tables)
    assert names == {
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
