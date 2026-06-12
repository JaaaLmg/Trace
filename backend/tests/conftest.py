import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

_BACKEND = Path(__file__).resolve().parent.parent
_TRACE_ROOT = _BACKEND.parent
for p in (str(_BACKEND), str(_TRACE_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.db.base import Base  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.models import load_all_models  # noqa: E402


TRACE_TABLES = [
    "test_reports",
    "run_artifacts",
    "trace_steps",
    "run_events",
    "pytest_case_results",
    "generated_test_cases",
    "generated_test_files",
    "run_attempts",
    "run_plan_items",
    "test_runs",
    "test_plans",
    "strategy_versions",
    "project_snapshots",
    "projects",
]


def reset_trace_db() -> None:
    try:
        engine = get_engine()
        engine.dispose()
        load_all_models()
        Base.metadata.create_all(bind=engine)
        with Session(engine) as session:
            for table in TRACE_TABLES:
                session.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
            session.commit()
    except RuntimeError as exc:
        pytest.skip(f"TRACE_DB_URL 未配置，跳过 PostgreSQL 集成测试: {exc}")
    except OperationalError as exc:
        pytest.skip(f"PostgreSQL 不可用，跳过数据库集成测试: {exc}")


@pytest.fixture
def clean_db():
    reset_trace_db()
