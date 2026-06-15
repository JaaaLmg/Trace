from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.repositories.versioning import get_prompt_version, get_tool_schema_version
from app.schemas.api_strategy import StrategyVersionCreate, StrategyVersionOut
from app.schemas.api_versioning import (
    PromptVersionCreate,
    PromptVersionOut,
    StrategyCreate,
    StrategyOut,
    ToolSchemaVersionCreate,
    ToolSchemaVersionOut,
)
from app.services.versioning import (
    create_prompt_version,
    create_strategy,
    create_strategy_version,
    create_tool_schema_version,
    list_all_strategies,
    list_versions_for_strategy,
)

router = APIRouter(tags=["versioning"])


# ---------- prompt versions ----------
@router.post("/api/v1/prompt-versions", response_model=PromptVersionOut)
def create_prompt_version_route(body: PromptVersionCreate, db: Session = Depends(get_db)):
    return create_prompt_version(
        db, name=body.name, version=body.version, content=body.content, source_ref=body.source_ref
    )


@router.get("/api/v1/prompt-versions/{prompt_version_id}", response_model=PromptVersionOut)
def get_prompt_version_route(prompt_version_id: str, db: Session = Depends(get_db)):
    prompt_version = get_prompt_version(db, prompt_version_id)
    if prompt_version is None:
        raise HTTPException(status_code=404, detail="prompt version not found")
    return prompt_version


# ---------- tool schema versions ----------
@router.post("/api/v1/tool-schema-versions", response_model=ToolSchemaVersionOut)
def create_tool_schema_version_route(body: ToolSchemaVersionCreate, db: Session = Depends(get_db)):
    return create_tool_schema_version(db, version=body.version, schema_json=body.schema_payload)


@router.get("/api/v1/tool-schema-versions/{tool_schema_version_id}", response_model=ToolSchemaVersionOut)
def get_tool_schema_version_route(tool_schema_version_id: str, db: Session = Depends(get_db)):
    tool_schema_version = get_tool_schema_version(db, tool_schema_version_id)
    if tool_schema_version is None:
        raise HTTPException(status_code=404, detail="tool schema version not found")
    return tool_schema_version


# ---------- strategies ----------
@router.post("/api/v1/strategies", response_model=StrategyOut)
def create_strategy_route(body: StrategyCreate, db: Session = Depends(get_db)):
    try:
        return create_strategy(db, name=body.name, workflow_type=body.workflow_type, strategy_id=body.strategy_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/api/v1/strategies", response_model=list[StrategyOut])
def list_strategies_route(db: Session = Depends(get_db)):
    return list_all_strategies(db)


@router.post("/api/v1/strategies/{strategy_id}/versions", response_model=StrategyVersionOut)
def create_strategy_version_route(strategy_id: str, body: StrategyVersionCreate, db: Session = Depends(get_db)):
    try:
        return create_strategy_version(
            db,
            strategy_id=strategy_id,
            name=body.name,
            version=body.version,
            prompt_version_id=body.prompt_version_id,
            tool_schema_version_id=body.tool_schema_version_id,
            model_provider=body.model_provider,
            model_name=body.model_name,
            model_params=body.model_params,
            temperature=body.temperature,
            allow_reflection=body.allow_reflection,
            max_tool_calls=body.max_tool_calls,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/api/v1/strategies/{strategy_id}/versions", response_model=list[StrategyVersionOut])
def list_strategy_versions_route(strategy_id: str, db: Session = Depends(get_db)):
    try:
        return list_versions_for_strategy(db, strategy_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
