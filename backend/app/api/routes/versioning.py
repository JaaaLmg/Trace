from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.api_versioning import PromptVersionOut, StrategyOut, ToolSchemaVersionOut

router = APIRouter(tags=["versioning"])


@router.get("/api/v1/strategies", response_model=list[StrategyOut])
def list_strategies_route(db: Session = Depends(get_db)):
    from sqlalchemy import select

    from app.models.versioning import Strategy

    stmt = select(Strategy).order_by(Strategy.created_at.asc())
    return list(db.scalars(stmt))


@router.get("/api/v1/prompt-versions/{prompt_version_id}", response_model=PromptVersionOut)
def get_prompt_version_route(prompt_version_id: str, db: Session = Depends(get_db)):
    from app.repositories.versioning import get_prompt_version

    prompt_version = get_prompt_version(db, prompt_version_id)
    if prompt_version is None:
        raise HTTPException(status_code=404, detail="prompt version not found")
    return prompt_version


@router.get("/api/v1/tool-schema-versions/{tool_schema_version_id}", response_model=ToolSchemaVersionOut)
def get_tool_schema_version_route(tool_schema_version_id: str, db: Session = Depends(get_db)):
    from app.repositories.versioning import get_tool_schema_version

    tool_schema_version = get_tool_schema_version(db, tool_schema_version_id)
    if tool_schema_version is None:
        raise HTTPException(status_code=404, detail="tool schema version not found")
    return tool_schema_version
