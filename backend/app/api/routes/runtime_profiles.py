from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.deps import get_db
from app.models import EvalTask, ProjectSnapshot
from app.repositories.runtime_profiles import get_runtime_profile, list_active_runtime_profiles_for_project
from app.schemas.api_runtime_profile import RuntimeProfileCreate, RuntimeProfileOut, RuntimeProfileUpdate
from app.services.projects import get_project_or_404
from app.services.runtime_profiles import (
    archive_runtime_profile,
    create_runtime_profile,
    ensure_default_runtime_profile,
    update_runtime_profile,
)
from app.tools.executor import docker_available

router = APIRouter(tags=["runtime-profiles"])


@router.post("/api/v1/projects/{project_id}/runtime-profiles", response_model=RuntimeProfileOut)
def create_project_runtime_profile_route(project_id: str, body: RuntimeProfileCreate, db: Session = Depends(get_db)):
    try:
        return create_runtime_profile(
            db,
            project_id=project_id,
            name=body.name,
            executor=body.executor,
            image=body.image,
            working_dir=body.working_dir,
            test_command=body.test_command,
            python_version=body.python_version,
            install_command=body.install_command,
            env_template=body.env_template,
            resource_limits=body.resource_limits,
            network_policy=body.network_policy,
            timeout_seconds=body.timeout_seconds,
            artifact_policy=body.artifact_policy,
            cleanup_policy=body.cleanup_policy,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _project_id_for_dataset(db: Session, dataset_id: str) -> str:
    snapshot_id = db.scalar(
        select(EvalTask.project_snapshot_id)
        .where(EvalTask.dataset_id == dataset_id)
        .order_by(EvalTask.created_at.asc(), EvalTask.id.asc())
    )
    if not snapshot_id:
        raise HTTPException(status_code=404, detail="dataset has no eval tasks")
    snapshot = db.get(ProjectSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="dataset project snapshot not found")
    return snapshot.project_id


@router.post("/api/v1/eval-datasets/{dataset_id}/runtime-profiles", response_model=RuntimeProfileOut)
def create_dataset_runtime_profile_route(dataset_id: str, body: RuntimeProfileCreate, db: Session = Depends(get_db)):
    project_id = _project_id_for_dataset(db, dataset_id)
    try:
        return create_runtime_profile(
            db,
            project_id=project_id,
            name=body.name,
            executor=body.executor,
            image=body.image,
            working_dir=body.working_dir,
            test_command=body.test_command,
            python_version=body.python_version,
            install_command=body.install_command,
            env_template=body.env_template,
            resource_limits=body.resource_limits,
            network_policy=body.network_policy,
            timeout_seconds=body.timeout_seconds,
            artifact_policy=body.artifact_policy,
            cleanup_policy=body.cleanup_policy,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/api/v1/projects/{project_id}/runtime-profiles", response_model=list[RuntimeProfileOut])
def list_project_runtime_profiles_route(project_id: str, db: Session = Depends(get_db)):
    try:
        project = get_project_or_404(db, project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    profiles = list_active_runtime_profiles_for_project(db, project.id)
    if not profiles:
        # 第一次访问时给个默认 profile，保证 run 创建链路有可绑定对象。
        return [ensure_default_runtime_profile(db, project_id=project.id)]
    return profiles


@router.get("/api/v1/eval-datasets/{dataset_id}/runtime-profiles", response_model=list[RuntimeProfileOut])
def list_dataset_runtime_profiles_route(dataset_id: str, db: Session = Depends(get_db)):
    project_id = _project_id_for_dataset(db, dataset_id)
    profiles = list_active_runtime_profiles_for_project(db, project_id)
    if not profiles:
        return [ensure_default_runtime_profile(db, project_id=project_id)]
    return profiles


@router.get("/api/v1/runtime-profiles/executors/status")
def executor_status_route():
    docker_ok, docker_reason = docker_available()
    return {
        "executors": {
            "local_subprocess": {
                "available": True,
                "isolation_level": "process",
                "network_enforced": False,
                "resource_limits_enforced": False,
                "warning": "local_subprocess is not a security sandbox",
            },
            "docker": {
                "available": docker_ok,
                "isolation_level": "container",
                "network_enforced": True,
                "resource_limits_enforced": True,
                "unavailable_reason": docker_reason,
            },
        }
    }


@router.get("/api/v1/runtime-profiles/{runtime_profile_id}", response_model=RuntimeProfileOut)
def get_runtime_profile_route(runtime_profile_id: str, db: Session = Depends(get_db)):
    profile = get_runtime_profile(db, runtime_profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="runtime profile not found")
    return profile


@router.patch("/api/v1/runtime-profiles/{runtime_profile_id}", response_model=RuntimeProfileOut)
def update_runtime_profile_route(runtime_profile_id: str, body: RuntimeProfileUpdate, db: Session = Depends(get_db)):
    try:
        return update_runtime_profile(
            db,
            profile_id=runtime_profile_id,
            updates=body.model_dump(exclude_unset=True),
        )
    except ValueError as e:
        status = 404 if "not found" in str(e) else 400
        raise HTTPException(status_code=status, detail=str(e)) from e


@router.post("/api/v1/runtime-profiles/{runtime_profile_id}/archive", response_model=RuntimeProfileOut)
def archive_runtime_profile_route(runtime_profile_id: str, db: Session = Depends(get_db)):
    try:
        return archive_runtime_profile(db, profile_id=runtime_profile_id)
    except ValueError as e:
        status = 404 if "not found" in str(e) else 400
        raise HTTPException(status_code=status, detail=str(e)) from e
