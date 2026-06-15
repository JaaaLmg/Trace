from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.strategy import StrategyVersion


def get_strategy_version(session: Session, strategy_id: str) -> StrategyVersion | None:
    return session.get(StrategyVersion, strategy_id)


def list_strategy_versions_for_strategy(session: Session, strategy_id: str) -> list[StrategyVersion]:
    stmt = (
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.created_at.asc())
    )
    return list(session.scalars(stmt))


def add_strategy_version(session: Session, strategy_version: StrategyVersion) -> StrategyVersion:
    session.add(strategy_version)
    session.commit()
    session.refresh(strategy_version)
    return strategy_version
