from __future__ import annotations

from celery import Celery

from app.db.redis_settings import get_redis_url


def create_celery_app() -> Celery:
    # Celery 是 B 线异步执行平面的核心入口。
    # broker/backend 统一复用 Redis，V1 先保持最小配置。
    redis_url = get_redis_url()
    app = Celery(
        "trace_backend",
        broker=redis_url,
        backend=redis_url,
        include=["app.workers.tasks"],
    )
    # 所有 run 默认进入同一个测试执行队列。
    app.conf.task_default_queue = "trace_test_runs"
    # 统一使用 JSON 序列化，避免传递复杂 Python 对象。
    app.conf.task_serializer = "json"
    app.conf.result_serializer = "json"
    app.conf.accept_content = ["json"]
    return app


celery_app = create_celery_app()
