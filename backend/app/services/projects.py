from __future__ import annotations

from pathlib import Path

from app.core.ids import new_id
from app.models.project import Project, ProjectSnapshot
from app.repositories.projects import add_project, add_snapshot, get_project, list_projects, list_snapshots
from sqlalchemy.orm import Session


def create_project(session: Session, *, name: str, local_path: str, description: str | None = None) -> Project:
    project = Project(
        id=new_id(),
        name=name,
        description=description,
        source_type="local_path",
        local_path=str(Path(local_path)),
    )
    return add_project(session, project)


def get_project_or_404(session: Session, project_id: str) -> Project:
    project = get_project(session, project_id)
    if project is None:
        raise ValueError("project not found")
    return project


def create_snapshot(session: Session, *, project_id: str, root_path: str | None = None) -> ProjectSnapshot:
    project = get_project_or_404(session, project_id)
    snapshot = ProjectSnapshot(
        id=new_id(),
        project_id=project.id,
        source_kind="local_path",
        root_path=str(Path(root_path or project.local_path)),
    )
    return add_snapshot(session, snapshot)


__all__ = ["create_project", "create_snapshot", "get_project_or_404", "list_projects", "list_snapshots"]
