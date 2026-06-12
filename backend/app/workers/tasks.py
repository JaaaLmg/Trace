from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.services.test_runs import execute_run_sync
from app.workers.celery_app import celery_app


@celery_app.task(name="trace.execute_run")
def execute_run_task(run_id: str, budget_override: dict | None = None) -> str:
    with Session(get_engine()) as session:
        run = execute_run_sync(session, run_id=run_id, budget_override=budget_override)
        return run.id
