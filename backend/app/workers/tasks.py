from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.services.test_runs import execute_run_sync
from app.workers.celery_app import celery_app


@celery_app.task(name="trace.execute_run")
def execute_run_task(run_id: str, budget_override: dict | None = None) -> str:
    # Worker 真正消费的任务函数。
    # 输入只保留 run_id，所有项目/计划/策略上下文都从数据库重新加载，
    # 这样队列消息更小，也避免把瞬时对象塞进 Redis。
    with Session(get_engine()) as session:
        run = execute_run_sync(session, run_id=run_id, budget_override=budget_override)
        return run.id
