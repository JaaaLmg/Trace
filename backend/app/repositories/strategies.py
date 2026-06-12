from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.strategy import StrategyVersion


def get_strategy_version(session: Session, strategy_id: str) -> StrategyVersion | None:
    return session.get(StrategyVersion, strategy_id)
