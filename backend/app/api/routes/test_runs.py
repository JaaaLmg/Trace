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
    run = get_test_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.post("/api/v1/test-runs/{run_id}/cancel")
def cancel_run_route(run_id: str, db: Session = Depends(get_db)):
    try:
        return cancel_run(db, run_id=run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/api/v1/test-runs/{run_id}/retry")
def retry_run_route(run_id: str, db: Session = Depends(get_db)):
    try:
        return retry_run_async(db, run_id=run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/api/v1/test-runs/{run_id}/trace-steps")
def list_trace_steps_route(run_id: str, db: Session = Depends(get_db)):
    return list_trace_steps(db, run_id)


@router.get("/api/v1/test-runs/{run_id}/events")
def list_run_events_route(run_id: str, db: Session = Depends(get_db)):
    return list_run_events(db, run_id)


@router.get("/api/v1/test-runs/{run_id}/attempts")
def list_run_attempts_route(run_id: str, db: Session = Depends(get_db)):
    return list_run_attempts(db, run_id)


@router.get("/api/v1/test-runs/{run_id}/pytest-results")
def list_pytest_results_route(run_id: str, db: Session = Depends(get_db)):
    return list_pytest_results(db, run_id)


@router.get("/api/v1/test-runs/{run_id}/artifacts")
def list_artifacts_route(run_id: str, db: Session = Depends(get_db)):
    return list_run_artifacts(db, run_id)


@router.get("/api/v1/test-runs/{run_id}/report")
def get_report_route(run_id: str, db: Session = Depends(get_db)):
    report = get_report(db, run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return report


@router.patch("/api/v1/generated-test-cases/{case_id}/adoption")
def patch_adoption_route(case_id: str, body: AdoptionPatchRequest, db: Session = Depends(get_db)):
    case = db.get(GeneratedTestCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="generated test case not found")
    case.adoption_status = body.adoption_status
    if body.human_meaningfulness_score is not None:
        case.human_meaningfulness_score = body.human_meaningfulness_score
    db.commit()
    db.refresh(case)
    return case
