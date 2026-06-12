from __future__ import annotations

from app.core.ids import new_id
from app.models.test_plan import TestPlan
from app.repositories.projects import get_project
from app.repositories.strategies import get_strategy_version
from app.repositories.test_plans import add_test_plan, get_test_plan
from sqlalchemy.orm import Session


def create_test_plan(
    session: Session,
    *,
    project_id: str,
    name: str,
    target_scope: list[str],
    goal: str,
    budget: dict | None = None,
    output_options: dict | None = None,
    default_strategy_version_id: str | None = None,
) -> TestPlan:
    if get_project(session, project_id) is None:
        raise ValueError("project not found")
    if default_strategy_version_id and get_strategy_version(session, default_strategy_version_id) is None:
        raise ValueError("strategy not found")
    plan = TestPlan(
        id=new_id(),
        project_id=project_id,
        name=name,
        target_scope=target_scope,
        goal=goal,
        budget=budget or {},
        output_options=output_options or {},
        default_strategy_version_id=default_strategy_version_id,
    )
    return add_test_plan(session, plan)


def get_test_plan_or_404(session: Session, plan_id: str) -> TestPlan:
    plan = get_test_plan(session, plan_id)
    if plan is None:
        raise ValueError("test plan not found")
    return plan
