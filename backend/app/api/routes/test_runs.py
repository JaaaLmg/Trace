from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.artifacts import GeneratedTestCase
from app.repositories.test_runs import (
    get_report,
    get_test_run,
    list_pytest_results,
    list_run_artifacts,
    list_run_attempts,
    list_run_events,
    list_trace_steps,
)
from app.schemas.api_run import AdoptionPatchRequest, RunCreateRequest
from app.services.test_runs import cancel_run, create_run, enqueue_run, retry_run_async

router = APIRouter(tags=["test-runs"])


@router.post("/api/v1/test-plans/{plan_id}/runs")
def create_run_route(plan_id: str, body: RunCreateRequest, db: Session = Depends(get_db)):
    # 创建一次具体执行，并立即投递到 Celery。
    # 这里做两步：先建 test_runs 主记录，再入 Redis 队列。
    try:
        run = create_run(
            db,
            plan_id=plan_id,
            snapshot_id=body.snapshot_id,
            strategy_version_id=body.strategy_version_id,
            budget_override=body.budget_override,
            output_options=body.output_options,
        )
        run = enqueue_run(db, run_id=run.id, budget_override=body.budget_override)
        return run
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/api/v1/test-runs/{run_id}")
def get_run_route(run_id: str, db: Session = Depends(get_db)):
    # 返回 run 主记录，前端轮询状态、展示摘要、读取错误信息都依赖这里。
    run = get_test_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.post("/api/v1/test-runs/{run_id}/cancel")
def cancel_run_route(run_id: str, db: Session = Depends(get_db)):
    # V1 的软取消接口：把 run 状态改为 cancelled。
    # 当前不会强杀已经启动的 pytest/子进程，这是后续增强项。
    try:
        return cancel_run(db, run_id=run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/api/v1/test-runs/{run_id}/retry")
def retry_run_route(run_id: str, db: Session = Depends(get_db)):
    # 重试不是在原 run 上追加 attempt，而是新建一条 test_runs，
    # 再通过 retry_of_run_id 指回旧 run，这样历史链路更清楚。
    try:
        return retry_run_async(db, run_id=run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/api/v1/test-runs/{run_id}/trace-steps")
def list_trace_steps_route(run_id: str, db: Session = Depends(get_db)):
    # 返回 run 的过程轨迹，用于时间线页面展示每一步 LLM/tool/report 行为。
    return list_trace_steps(db, run_id)


@router.get("/api/v1/test-runs/{run_id}/events")
def list_run_events_route(run_id: str, db: Session = Depends(get_db)):
    # 返回状态机事件流，主要帮助前端理解 queued/running/completed 的变迁过程。
    return list_run_events(db, run_id)


@router.get("/api/v1/test-runs/{run_id}/attempts")
def list_run_attempts_route(run_id: str, db: Session = Depends(get_db)):
    # 返回所有 attempt，前端可据此区分 initial 与 reflection，以及每轮是否成功。
    return list_run_attempts(db, run_id)


@router.get("/api/v1/test-runs/{run_id}/pytest-results")
def list_pytest_results_route(run_id: str, db: Session = Depends(get_db)):
    # 返回 pytest 用例级结果，是报告页和结果表格的核心数据源。
    return list_pytest_results(db, run_id)


@router.get("/api/v1/test-runs/{run_id}/artifacts")
def list_artifacts_route(run_id: str, db: Session = Depends(get_db)):
    # 返回 run 产物，如 report.md / report.json，后续也可扩展 junit、日志等文件。
    return list_run_artifacts(db, run_id)


@router.get("/api/v1/test-runs/{run_id}/report")
def get_report_route(run_id: str, db: Session = Depends(get_db)):
    # 返回结构化测试报告摘要。前端一般先取这里，再按需打开 markdown/json 文件。
    report = get_report(db, run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return report


@router.patch("/api/v1/generated-test-cases/{case_id}/adoption")
def patch_adoption_route(case_id: str, body: AdoptionPatchRequest, db: Session = Depends(get_db)):
    # 记录人工对生成用例的采纳结果，方便后续前端打标和人工质量回流。
    case = db.get(GeneratedTestCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="generated test case not found")
    case.adoption_status = body.adoption_status
    if body.human_meaningfulness_score is not None:
        case.human_meaningfulness_score = body.human_meaningfulness_score
    db.commit()
    db.refresh(case)
    return case
