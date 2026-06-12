from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.strategy import StrategyVersion


def get_strategy_version(session: Session, strategy_id: str) -> StrategyVersion | None:
    return session.get(StrategyVersion, strategy_id)


def list_strategy_versions(session: Session) -> list[StrategyVersion]:
    return list(session.scalars(select(StrategyVersion).order_by(StrategyVersion.id.asc())))
