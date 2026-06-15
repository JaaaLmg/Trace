from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.versioning import PromptVersion, Strategy, ToolSchemaVersion


def get_strategy(session: Session, strategy_id: str) -> Strategy | None:
    return session.get(Strategy, strategy_id)


def get_prompt_version(session: Session, prompt_version_id: str) -> PromptVersion | None:
    return session.get(PromptVersion, prompt_version_id)


def get_tool_schema_version(session: Session, tool_schema_version_id: str) -> ToolSchemaVersion | None:
    return session.get(ToolSchemaVersion, tool_schema_version_id)
