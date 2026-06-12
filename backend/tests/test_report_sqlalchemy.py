from pathlib import Path

from app.agents.llm import MockLLM
from app.agents.orchestrator import execute_run
from app.agents.runtime import PlanInput
from app.agents.seeds import SEED_STRATEGIES
from app.core.ids import new_id
from app.db.session import get_engine
from app.models.project import Project, ProjectSnapshot
from app.models.strategy import StrategyVersion
from app.recorders.sqlalchemy_recorder import SQLAlchemyRunRecorder
from app.schemas.records import TestRunRecord
from app.tools import default_registry
from app.tools.base import ToolContext
from sqlalchemy.orm import Session


def _responder(messages):
    blob = "\n".join(m.content for m in messages)
    if "TASK: GENERATE" in blob:
        return '{"test_file_content":"from calc import add\\n\\ndef test_add():\\n    assert add(2, 3) == 5\\n","cases":[{"test_name":"test_add","target_function":"add","assertion_summary":"2+3=5"}],"coverage_notes":"db report"}'
    raise AssertionError(blob[:120])


def test_report_metrics_work_with_sqlalchemy_recorder(tmp_path, clean_db):
    from app.models.test_plan import TestPlan as TestPlanModel

    engine = get_engine()

    root = tmp_path / "proj"
    root.mkdir()
    (root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    with Session(engine) as session:
        project = Project(id=new_id(), name="demo", local_path=str(root))
        snapshot = ProjectSnapshot(id=new_id(), project_id=project.id, source_kind="local_path", root_path=str(root))
        strategy = StrategyVersion(id="sv-direct-v1", name="Direct v1", workflow_type="direct")
        plan = TestPlanModel(
            id=new_id(),
            project_id=project.id,
            name="demo-plan",
            target_scope=[],
            goal="测试 calc 模块",
            default_strategy_version_id=strategy.id,
        )
        session.add_all([project, snapshot, strategy, plan])
        session.commit()

        recorder = SQLAlchemyRunRecorder(session)
        run = TestRunRecord(test_plan_id=plan.id, project_snapshot_id=snapshot.id, strategy_version_id="sv-direct-v1")
        outcome = execute_run(
            tools=ToolContext(root=root, test_write_dir=root / "tests" / "generated"),
            registry=default_registry(),
            llm=MockLLM(_responder),
            recorder=recorder,
            strategy_spec=SEED_STRATEGIES["direct"],
            plan_input=PlanInput(target_scope=[], goal="测试 calc 模块"),
            run=run,
            artifacts_dir=root / "artifacts",
        )

        assert outcome.run.status == "completed"
        assert outcome.report is not None
        assert outcome.report.metrics["attempts"] >= 1
        assert outcome.report.metrics["final_passed"] >= 1
