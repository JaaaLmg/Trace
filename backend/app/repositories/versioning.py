from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.versioning import PromptVersion, Strategy, ToolSchemaVersion


def get_strategy(session: Session, strategy_id: str) -> Strategy | None:
    return session.get(Strategy, strategy_id)


def get_prompt_version(session: Session, prompt_version_id: str) -> PromptVersion | None:
    return session.get(PromptVersion, prompt_version_id)


def get_tool_schema_version(session: Session, tool_schema_version_id: str) -> ToolSchemaVersion | None:
    return session.get(ToolSchemaVersion, tool_schema_version_id)


def list_strategies(session: Session) -> list[Strategy]:
    return list(session.scalars(select(Strategy).order_by(Strategy.created_at.asc())))


def add_strategy(session: Session, strategy: Strategy) -> Strategy:
    session.add(strategy)
    session.commit()
    session.refresh(strategy)
    return strategy


def add_prompt_version(session: Session, prompt_version: PromptVersion) -> PromptVersion:
    session.add(prompt_version)
    session.commit()
    session.refresh(prompt_version)
    return prompt_version


def add_tool_schema_version(session: Session, tool_schema_version: ToolSchemaVersion) -> ToolSchemaVersion:
    session.add(tool_schema_version)
    session.commit()
    session.refresh(tool_schema_version)
    return tool_schema_version
