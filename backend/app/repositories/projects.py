from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project, ProjectSnapshot


def add_project(session: Session, project: Project) -> Project:
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def list_projects(session: Session) -> list[Project]:
    return list(session.scalars(select(Project).order_by(Project.created_at.desc())))


def get_project(session: Session, project_id: str) -> Project | None:
    return session.get(Project, project_id)


def add_snapshot(session: Session, snapshot: ProjectSnapshot) -> ProjectSnapshot:
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def list_snapshots(session: Session, project_id: str) -> list[ProjectSnapshot]:
    stmt = select(ProjectSnapshot).where(ProjectSnapshot.project_id == project_id).order_by(ProjectSnapshot.created_at.desc())
    return list(session.scalars(stmt))
