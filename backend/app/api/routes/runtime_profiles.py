from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.api_runtime_profile import RuntimeProfileOut
from app.services.projects import get_project_or_404
from app.services.runtime_profiles import ensure_default_runtime_profile

router = APIRouter(tags=["runtime-profiles"])


@router.get("/api/v1/projects/{project_id}/runtime-profiles", response_model=list[RuntimeProfileOut])
def list_project_runtime_profiles_route(project_id: str, db: Session = Depends(get_db)):
    try:
        project = get_project_or_404(db, project_id)
        return [ensure_default_runtime_profile(db, project_id=project.id)]
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/api/v1/runtime-profiles/{runtime_profile_id}", response_model=RuntimeProfileOut)
def get_runtime_profile_route(runtime_profile_id: str, db: Session = Depends(get_db)):
    from app.repositories.runtime_profiles import get_runtime_profile

    profile = get_runtime_profile(db, runtime_profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="runtime profile not found")
    return profile
