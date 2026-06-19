from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.api_evaluation import (
    ExperimentCleanupRequest,
    ExperimentCleanRunOut,
    ExperimentCreate,
    ExperimentOut,
    TestReplayOut,
)
from app.schemas.evaluation import ExperimentMetricsResponse
from app.services.experiments import (
    ExperimentError,
    cancel_experiment,
    create_experiment,
    enqueue_experiment,
    get_experiment,
    get_experiment_metrics,
    list_clean_runs,
    list_experiments,
    list_replay_runs,
)
from app.services.artifact_cleanup import CleanupError, cleanup_experiment_workspaces

router = APIRouter(tags=["experiments"])


def _experiment_http_error(error: ExperimentError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=str(error))


@router.post("/api/v1/experiments", response_model=ExperimentOut)
def create_experiment_route(body: ExperimentCreate, db: Session = Depends(get_db)):
    try:
        return create_experiment(
            db,
            experiment_id=body.id,
            name=body.name,
            dataset_id=body.dataset_id,
            runtime_profile_id=body.runtime_profile_id,
            strategy_version_ids=body.strategy_version_ids,
            repeat_count=body.repeat_count,
            llm_override=body.llm_override,
        )
    except ExperimentError as e:
        raise _experiment_http_error(e) from e


@router.get("/api/v1/experiments", response_model=list[ExperimentOut])
def list_experiments_route(db: Session = Depends(get_db)):
    return list_experiments(db)


@router.get("/api/v1/experiments/{experiment_id}", response_model=ExperimentOut)
def get_experiment_route(experiment_id: str, db: Session = Depends(get_db)):
    try:
        return get_experiment(db, experiment_id)
    except ExperimentError as e:
        raise _experiment_http_error(e) from e


@router.post("/api/v1/experiments/{experiment_id}/runs", response_model=ExperimentOut)
def run_experiment_route(experiment_id: str, db: Session = Depends(get_db)):
    try:
        return enqueue_experiment(db, experiment_id)
    except ExperimentError as e:
        raise _experiment_http_error(e) from e


@router.post("/api/v1/experiments/{experiment_id}/cancel", response_model=ExperimentOut)
def cancel_experiment_route(experiment_id: str, db: Session = Depends(get_db)):
    try:
        return cancel_experiment(db, experiment_id)
    except ExperimentError as e:
        raise _experiment_http_error(e) from e


@router.get("/api/v1/experiments/{experiment_id}/clean-runs", response_model=list[ExperimentCleanRunOut])
def list_clean_runs_route(experiment_id: str, db: Session = Depends(get_db)):
    try:
        return list_clean_runs(db, experiment_id)
    except ExperimentError as e:
        raise _experiment_http_error(e) from e


@router.get("/api/v1/experiments/{experiment_id}/replay-runs", response_model=list[TestReplayOut])
def list_replay_runs_route(experiment_id: str, db: Session = Depends(get_db)):
    try:
        return list_replay_runs(db, experiment_id)
    except ExperimentError as e:
        raise _experiment_http_error(e) from e


@router.get("/api/v1/experiments/{experiment_id}/metrics", response_model=ExperimentMetricsResponse)
def get_experiment_metrics_route(experiment_id: str, db: Session = Depends(get_db)):
    try:
        return get_experiment_metrics(db, experiment_id)
    except ExperimentError as e:
        raise _experiment_http_error(e) from e


@router.post("/api/v1/experiments/{experiment_id}/cleanup")
def cleanup_experiment_route(
    experiment_id: str,
    body: ExperimentCleanupRequest,
    db: Session = Depends(get_db),
):
    try:
        return cleanup_experiment_workspaces(
            db,
            experiment_id=experiment_id,
            dry_run=body.dry_run,
            keep_failed=body.keep_failed,
        )
    except CleanupError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

