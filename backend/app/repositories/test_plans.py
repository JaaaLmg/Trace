from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.test_plan import TestPlan


def add_test_plan(session: Session, plan: TestPlan) -> TestPlan:
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan


def get_test_plan(session: Session, plan_id: str) -> TestPlan | None:
    return session.get(TestPlan, plan_id)
