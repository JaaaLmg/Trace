from app.core.ids import new_id
from app.db.session import get_engine
from app.agents.recorder import InMemoryRecorder
from app.models.project import Project, ProjectSnapshot
from app.models.strategy import StrategyVersion
from app.models.test_run import RunAttempt as RunAttemptModel
from app.models.trace import TraceStep as TraceStepModel
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
from app.agents.final_attempts import final_attempts_by_item
from sqlalchemy import text
from sqlalchemy.orm import Session


def _seed_fk_prereqs(session: Session):
    from app.models.test_plan import TestPlan as TestPlanModel

    project_id = new_id()
    snapshot_id = new_id()
    strategy_id = "sv-recorder-test"
    plan_id = new_id()
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
    session.add(
        TestPlanModel(
            id=plan_id,
            project_id=project_id,
            name="recorder-plan",
            target_scope=[],
            goal="测试 recorder",
            default_strategy_version_id=strategy_id,
        )
    )
    session.commit()
    return project_id, snapshot_id, strategy_id, plan_id


def test_sqlalchemy_recorder_roundtrip(clean_db):
    engine = get_engine()

    with Session(engine) as session:
        _, snapshot_id, strategy_id, plan_id = _seed_fk_prereqs(session)
        recorder = SQLAlchemyRunRecorder(session)

        run = TestRunRecord(test_plan_id=plan_id, project_snapshot_id=snapshot_id, strategy_version_id=strategy_id)
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
        recorder.save_report(
            TestReportRecord(
                run_id=run.id,
                summary="updated",
                metrics={"final_passed": 2},
                markdown_uri="backend/artifacts/demo2.md",
                json_uri="backend/artifacts/demo2.json",
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
        saved_report = session.execute(
            text("select summary, metrics from test_reports where run_id = :run_id"),
            {"run_id": run.id},
        ).one()
        assert saved_report.summary == "updated"
        assert saved_report.metrics == {"final_passed": 2}
        assert [x.id for x in recorder.list_plan_items(run.id)] == [item.id]
        assert [x.id for x in recorder.list_attempts(run.id)] == [attempt.id]
        assert [x.id for x in recorder.list_pytest_results(run.id)] == [result.id]


def test_sqlalchemy_recorder_query_methods_return_record_contracts(clean_db):
    engine = get_engine()

    with Session(engine) as session:
        _, snapshot_id, strategy_id, plan_id = _seed_fk_prereqs(session)
        db_recorder = SQLAlchemyRunRecorder(session)
        mem_recorder = InMemoryRecorder()

        run = TestRunRecord(test_plan_id=plan_id, project_snapshot_id=snapshot_id, strategy_version_id=strategy_id)
        db_recorder.save_run(run)
        mem_recorder.save_run(run)

        item = RunPlanItemRecord(
            run_id=run.id,
            index=0,
            target_type="function",
            target_ref="calc.add",
            goal="测试 add",
            planned_assertions=["returns sum"],
            status="done",
        )
        attempt1 = RunAttemptRecord(
            run_plan_item_id=item.id,
            attempt_no=1,
            kind="initial",
            status="failed",
            pytest_exit_code=1,
        )
        attempt2 = RunAttemptRecord(
            run_plan_item_id=item.id,
            attempt_no=2,
            kind="reflection",
            status="passed",
            pytest_exit_code=0,
            reflection_reason="fix assertion",
        )
        generated_file = GeneratedTestFileRecord(
            attempt_id=attempt2.id,
            path="tests/generated/test_calc.py",
            content_text="def test_add():\n    assert True\n",
            content_hash="hash-file",
            generation_reason="reflection fix",
        )
        case = GeneratedTestCaseRecord(
            file_id=generated_file.id,
            nodeid="tests/generated/test_calc.py::test_add",
            test_name="test_add",
            start_line=1,
            end_line=2,
            target_function="add",
            assertion_summary="returns sum",
            source_strategy_version_id=strategy_id,
            adoption_status="adopted",
            human_meaningfulness_score=4,
            rule_flags=["strong_assertion"],
        )
        result = PytestCaseResultRecord(
            attempt_id=attempt2.id,
            generated_test_case_id=case.id,
            nodeid="tests/generated/test_calc.py::test_add",
            mapping_status="matched",
            status="passed",
            duration_ms=12,
        )

        for recorder in (db_recorder, mem_recorder):
            recorder.add_plan_item(item)
            recorder.add_attempt(attempt1)
            recorder.add_attempt(attempt2)
            recorder.add_generated_file(generated_file)
            recorder.add_generated_cases([case])
            recorder.add_pytest_results([result])

        db_plan_items = db_recorder.list_plan_items(run.id)
        db_attempts = db_recorder.list_attempts(run.id)
        db_results = db_recorder.list_pytest_results(run.id)
        db_files = db_recorder.list_generated_files(run.id)
        db_cases = db_recorder.list_generated_cases(run.id)

        assert db_plan_items == mem_recorder.list_plan_items(run.id)
        assert db_attempts == mem_recorder.list_attempts(run.id)
        assert db_results == mem_recorder.list_pytest_results(run.id)
        assert db_files == mem_recorder.list_generated_files(run.id)
        assert db_cases == mem_recorder.list_generated_cases(run.id)
        assert isinstance(db_plan_items[0], RunPlanItemRecord)
        assert isinstance(db_attempts[0], RunAttemptRecord)
        assert isinstance(db_results[0], PytestCaseResultRecord)
        assert isinstance(db_files[0], GeneratedTestFileRecord)
        assert isinstance(db_cases[0], GeneratedTestCaseRecord)
        assert not isinstance(db_attempts[0], RunAttemptModel)
        assert final_attempts_by_item(db_recorder, run.id)[item.id] == attempt2


def test_sqlalchemy_recorder_does_not_overwrite_cancelled_run(clean_db):
    from app.models.test_run import TestRun as TestRunModel

    engine = get_engine()

    with Session(engine) as session:
        _, snapshot_id, strategy_id, plan_id = _seed_fk_prereqs(session)
        recorder = SQLAlchemyRunRecorder(session)
        run = TestRunRecord(test_plan_id=plan_id, project_snapshot_id=snapshot_id, strategy_version_id=strategy_id)
        run.status = "running"
        recorder.save_run(run)

        with Session(engine) as canceller:
            stored = canceller.get(TestRunModel, run.id)
            assert stored is not None
            stored.status = "cancelled"
            canceller.commit()

        run.status = "completed"
        run.stage = "reporting"
        run.pytest_summary = {"passed": 1}
        recorder.save_run(run)

    with Session(engine) as session:
        stored = session.get(TestRunModel, run.id)
        assert stored is not None
        assert stored.status == "cancelled"
        assert stored.pytest_summary == {"passed": 1}


def test_sqlalchemy_recorder_clips_trace_step_short_columns(clean_db):
    engine = get_engine()

    with Session(engine) as session:
        _, snapshot_id, strategy_id, plan_id = _seed_fk_prereqs(session)
        recorder = SQLAlchemyRunRecorder(session)
        run = TestRunRecord(test_plan_id=plan_id, project_snapshot_id=snapshot_id, strategy_version_id=strategy_id)
        recorder.save_run(run)
        long_text = "x" * 1000

        recorder.add_trace_step(
            TraceStep(
                run_id=run.id,
                step_index=1,
                step_type="generation",
                name=long_text,
                status="error",
                error=long_text,
                payload={"full_error": long_text},
            )
        )

        stored = session.query(TraceStepModel).filter_by(run_id=run.id).one()
        assert len(stored.name) <= 255
        assert len(stored.error) <= 255
        assert stored.name.endswith("...<truncated>")
        assert stored.error.endswith("...<truncated>")
        assert stored.payload == {"full_error": long_text}
