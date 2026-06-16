from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.services.experiments import run_experiment
from app.services.test_runs import execute_run_sync
from app.repositories.test_runs import get_test_run
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="trace.execute_run")
def execute_run_task(run_id: str, budget_override: dict | None = None) -> str:
    # Worker 真正消费的任务函数。
    # 输入只保留 run_id，所有项目/计划/策略上下文都从数据库重新加载，
    # 这样队列消息更小，也避免把瞬时对象塞进 Redis。
    with Session(get_engine()) as session:
        try:
            run = execute_run_sync(session, run_id=run_id, budget_override=budget_override)
        except Exception:
            logger.warning("Run %s failed during worker execution; status was persisted.", run_id, exc_info=True)
            run = get_test_run(session, run_id)
            if run is None:
                raise
        return run.id


@celery_app.task(name="trace.execute_experiment")
def execute_experiment_task(experiment_id: str) -> str:
    with Session(get_engine()) as session:
        try:
            run_experiment(session, experiment_id)
        except Exception:
            logger.warning("Experiment %s failed during worker execution.", experiment_id, exc_info=True)
            raise
        return experiment_id
