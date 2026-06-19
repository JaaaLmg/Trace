from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.runtime_profile import RuntimeProfile


def get_runtime_profile(session: Session, profile_id: str) -> RuntimeProfile | None:
    return session.get(RuntimeProfile, profile_id)


def list_runtime_profiles_for_project(session: Session, project_id: str) -> list[RuntimeProfile]:
    stmt = select(RuntimeProfile).where(RuntimeProfile.project_id == project_id).order_by(RuntimeProfile.created_at.asc())
    return list(session.scalars(stmt))


def list_active_runtime_profiles_for_project(session: Session, project_id: str) -> list[RuntimeProfile]:
    stmt = (
        select(RuntimeProfile)
        .where(RuntimeProfile.project_id == project_id, RuntimeProfile.archived_at.is_(None))
        .order_by(RuntimeProfile.created_at.asc())
    )
    return list(session.scalars(stmt))


def add_runtime_profile(session: Session, profile: RuntimeProfile) -> RuntimeProfile:
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile
