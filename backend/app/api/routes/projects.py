from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.api_project import ProjectCreateRequest, ProjectOut, ProjectSnapshotOut, SnapshotCreateRequest
from app.services.projects import create_project, create_snapshot, get_project_or_404, list_projects, list_snapshots

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.post("", response_model=ProjectOut)
def create_project_route(body: ProjectCreateRequest, db: Session = Depends(get_db)):
    # 创建一个被测项目。V1 只支持本地路径项目，后续 run/snapshot 都从这里挂载。
    try:
        return create_project(db, name=body.name, local_path=body.local_path, description=body.description)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("", response_model=list[ProjectOut])
def list_projects_route(db: Session = Depends(get_db)):
    # 返回项目列表，给前端做项目首页或下拉选择。
    return list_projects(db)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project_route(project_id: str, db: Session = Depends(get_db)):
    # 查询单个项目详情，常用于进入项目详情页前拉基础信息。
    try:
        return get_project_or_404(db, project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{project_id}/snapshots", response_model=ProjectSnapshotOut)
def create_snapshot_route(project_id: str, body: SnapshotCreateRequest, db: Session = Depends(get_db)):
    # 为项目创建一次代码快照。V1 里快照本质上是一次 root_path 绑定，
    # run 必须绑定 snapshot，避免执行时直接依赖“当前项目路径”的隐式状态。
    try:
        return create_snapshot(db, project_id=project_id, root_path=body.root_path)
    except ValueError as e:
        status_code = 404 if "project not found" in str(e) else 400
        raise HTTPException(status_code=status_code, detail=str(e)) from e


@router.get("/{project_id}/snapshots", response_model=list[ProjectSnapshotOut])
def list_snapshots_route(project_id: str, db: Session = Depends(get_db)):
    # 列出项目已有快照，便于前端在创建 run 时选择代码版本/根目录。
    return list_snapshots(db, project_id)
