from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.settings import get_database_settings


def build_engine() -> Engine:
    settings = get_database_settings()
    return create_engine(settings.database_url, echo=settings.echo)


_ENGINE: Engine | None = None
_SESSION_FACTORY: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = build_engine()
    return _ENGINE


def get_session_factory() -> sessionmaker[Session]:
    global _SESSION_FACTORY
    if _SESSION_FACTORY is None:
        _SESSION_FACTORY = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, class_=Session)
    return _SESSION_FACTORY


engine = None
SessionLocal = None


def get_db():
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
