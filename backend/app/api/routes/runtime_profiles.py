from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.repositories.runtime_profiles import get_runtime_profile, list_runtime_profiles_for_project
from app.schemas.api_runtime_profile import RuntimeProfileCreate, RuntimeProfileOut
from app.services.projects import get_project_or_404
from app.services.runtime_profiles import create_runtime_profile, ensure_default_runtime_profile

router = APIRouter(tags=["runtime-profiles"])


@router.post("/api/v1/projects/{project_id}/runtime-profiles", response_model=RuntimeProfileOut)
def create_project_runtime_profile_route(project_id: str, body: RuntimeProfileCreate, db: Session = Depends(get_db)):
    try:
        return create_runtime_profile(
            db,
            project_id=project_id,
            name=body.name,
            test_command=body.test_command,
            python_version=body.python_version,
            install_command=body.install_command,
            env_template=body.env_template,
            resource_limits=body.resource_limits,
            network_policy=body.network_policy,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/api/v1/projects/{project_id}/runtime-profiles", response_model=list[RuntimeProfileOut])
def list_project_runtime_profiles_route(project_id: str, db: Session = Depends(get_db)):
    try:
        project = get_project_or_404(db, project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    profiles = list_runtime_profiles_for_project(db, project.id)
    if not profiles:
        # 第一次访问时给个默认 profile，保证 run 创建链路有可绑定对象。
        return [ensure_default_runtime_profile(db, project_id=project.id)]
    return profiles


@router.get("/api/v1/runtime-profiles/{runtime_profile_id}", response_model=RuntimeProfileOut)
def get_runtime_profile_route(runtime_profile_id: str, db: Session = Depends(get_db)):
    profile = get_runtime_profile(db, runtime_profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="runtime profile not found")
    return profile
