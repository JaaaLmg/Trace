from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.api_project import ProjectCreateRequest, SnapshotCreateRequest
from app.services.projects import create_project, create_snapshot, get_project_or_404, list_projects, list_snapshots

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.post("")
def create_project_route(body: ProjectCreateRequest, db: Session = Depends(get_db)):
    return create_project(db, name=body.name, local_path=body.local_path, description=body.description)


@router.get("")
def list_projects_route(db: Session = Depends(get_db)):
    return list_projects(db)


@router.get("/{project_id}")
def get_project_route(project_id: str, db: Session = Depends(get_db)):
    try:
        return get_project_or_404(db, project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{project_id}/snapshots")
def create_snapshot_route(project_id: str, body: SnapshotCreateRequest, db: Session = Depends(get_db)):
    try:
        return create_snapshot(db, project_id=project_id, root_path=body.root_path)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{project_id}/snapshots")
def list_snapshots_route(project_id: str, db: Session = Depends(get_db)):
    return list_snapshots(db, project_id)
