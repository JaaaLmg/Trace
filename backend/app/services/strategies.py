from __future__ import annotations

from app.agents.seeds import seed_list
from app.models.strategy import StrategyVersion
from app.repositories.strategies import get_strategy_version
from sqlalchemy.orm import Session


def seed_strategy_versions(session: Session) -> None:
    for spec in seed_list():
        if get_strategy_version(session, spec.id):
            continue
        session.add(
            StrategyVersion(
                id=spec.id,
                name=spec.name,
                workflow_type=spec.workflow_type,
                model_provider=spec.model_provider,
                model_name=spec.model_name,
                model_params=spec.model_params,
                allow_reflection=spec.allow_reflection,
                max_tool_calls=spec.max_tool_calls,
                prompt_ref=spec.prompt_ref,
                tool_schema_ref=spec.tool_schema_ref,
            )
        )
    session.commit()
