from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.test_plan import TestPlan


def add_test_plan(session: Session, plan: TestPlan) -> TestPlan:
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan


def get_test_plan(session: Session, plan_id: str) -> TestPlan | None:
    return session.get(TestPlan, plan_id)


def list_test_plans_for_project(session: Session, project_id: str) -> list[TestPlan]:
    stmt = (
        select(TestPlan)
        .where(TestPlan.project_id == project_id)
        .order_by(TestPlan.created_at.desc())
    )
    return list(session.scalars(stmt))
