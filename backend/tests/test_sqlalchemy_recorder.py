from app.core.ids import new_id
from app.db.base import Base
from app.db.session import get_engine
from app.models import load_all_models
from app.models.project import Project, ProjectSnapshot
from app.models.strategy import StrategyVersion
from app.recorders.sqlalchemy_recorder import SQLAlchemyRunRecorder
from app.schemas.records import (
    GeneratedTestCaseRecord,
    GeneratedTestFileRecord,
    PytestCaseResultRecord,
    RunArtifactRecord,
    RunAttemptRecord,
    RunPlanItemRecord,
    TestReportRecord,
    TestRunRecord,
)
from app.schemas.trace import RunEvent, TraceStep
from sqlalchemy import text
from sqlalchemy.orm import Session


def _seed_fk_prereqs(session: Session):
    project_id = new_id()
    snapshot_id = new_id()
    strategy_id = "sv-recorder-test"
    session.add(
        Project(
            id=project_id,
            name="demo",
            local_path="D:/demo",
        )
    )
    session.add(
        ProjectSnapshot(
            id=snapshot_id,
            project_id=project_id,
            source_kind="local_path",
            root_path="D:/demo",
        )
    )
    session.add(
        StrategyVersion(
            id=strategy_id,
            name="Recorder Test",
            workflow_type="direct",
        )
    )
    session.commit()
    return project_id, snapshot_id, strategy_id


def _truncate_all(session: Session):
    tables = [
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
    for table in tables:
        session.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
    session.commit()


def test_sqlalchemy_recorder_roundtrip():
    load_all_models()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        _truncate_all(session)
        _, snapshot_id, strategy_id = _seed_fk_prereqs(session)
        recorder = SQLAlchemyRunRecorder(session)

        run = TestRunRecord(project_snapshot_id=snapshot_id, strategy_version_id=strategy_id)
        run.status = "running"
        run.stage = "preparing"
        recorder.save_run(run)

        recorder.add_run_event(
            RunEvent(
                run_id=run.id,
                stage="preparing",
                event_type="stage_enter",
                status_before="queued",
                status_after="running",
                message="进入 preparing",
            )
        )
        recorder.add_trace_step(
            TraceStep(
                run_id=run.id,
                step_index=1,
                step_type="system",
                name="准备执行",
                status="ok",
            )
        )

        item = RunPlanItemRecord(run_id=run.id, index=0, target_type="goal", target_ref="all", goal="测试 demo")
        recorder.add_plan_item(item)

        attempt = RunAttemptRecord(run_plan_item_id=item.id, attempt_no=1, kind="initial")
        recorder.add_attempt(attempt)

        f = GeneratedTestFileRecord(
            attempt_id=attempt.id,
            path="tests/generated/test_demo.py",
            content_text="def test_ok():\n    assert True\n",
            content_hash="abc123",
        )
        recorder.add_generated_file(f)

        case = GeneratedTestCaseRecord(
            file_id=f.id,
            nodeid="tests/generated/test_demo.py::test_ok",
            test_name="test_ok",
            start_line=1,
            end_line=2,
        )
        recorder.add_generated_cases([case])

        result = PytestCaseResultRecord(
            attempt_id=attempt.id,
            generated_test_case_id=case.id,
            nodeid="tests/generated/test_demo.py::test_ok",
            status="passed",
            mapping_status="matched",
        )
        recorder.add_pytest_results([result])

        recorder.add_artifact(
            RunArtifactRecord(
                run_id=run.id,
                attempt_id=attempt.id,
                artifact_type="report_json",
                uri="backend/artifacts/demo.json",
            )
        )

        recorder.save_report(
            TestReportRecord(
                run_id=run.id,
                summary="ok",
                metrics={"final_passed": 1},
                markdown_uri="backend/artifacts/demo.md",
                json_uri="backend/artifacts/demo.json",
            )
        )

        counts = {
            "test_runs": session.execute(text("select count(*) from test_runs")).scalar_one(),
            "run_events": session.execute(text("select count(*) from run_events")).scalar_one(),
            "trace_steps": session.execute(text("select count(*) from trace_steps")).scalar_one(),
            "run_plan_items": session.execute(text("select count(*) from run_plan_items")).scalar_one(),
            "run_attempts": session.execute(text("select count(*) from run_attempts")).scalar_one(),
            "generated_test_files": session.execute(text("select count(*) from generated_test_files")).scalar_one(),
            "generated_test_cases": session.execute(text("select count(*) from generated_test_cases")).scalar_one(),
            "pytest_case_results": session.execute(text("select count(*) from pytest_case_results")).scalar_one(),
            "run_artifacts": session.execute(text("select count(*) from run_artifacts")).scalar_one(),
            "test_reports": session.execute(text("select count(*) from test_reports")).scalar_one(),
        }

        assert counts == {
            "test_runs": 1,
            "run_events": 1,
            "trace_steps": 1,
            "run_plan_items": 1,
            "run_attempts": 1,
            "generated_test_files": 1,
            "generated_test_cases": 1,
            "pytest_case_results": 1,
            "run_artifacts": 1,
            "test_reports": 1,
        }
