from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.models.strategy import StrategyVersion
from app.models.versioning import PromptVersion, Strategy, ToolSchemaVersion
from app.repositories.strategies import (
    add_strategy_version,
    get_strategy_version,
    list_strategy_versions_for_strategy,
)
from app.repositories.versioning import (
    add_prompt_version,
    add_strategy,
    add_tool_schema_version,
    get_prompt_version,
    get_strategy,
    get_tool_schema_version,
    list_strategies,
)


def hash_json(payload: dict) -> str:
    # content_hash 是复现主键之一：用规范化 JSON（排序键、紧凑分隔符）做 sha256，保证稳定可比。
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def create_prompt_version(
    session: Session, *, name: str, version: str, content: dict, source_ref: str | None = None
) -> PromptVersion:
    record = PromptVersion(
        id=f"pv-{new_id()}",
        name=name,
        version=version,
        content=content,
        content_hash=hash_json(content),
        source_ref=source_ref,
    )
    return add_prompt_version(session, record)


def create_tool_schema_version(session: Session, *, version: str, schema_json: dict) -> ToolSchemaVersion:
    record = ToolSchemaVersion(
        id=f"tsv-{new_id()}",
        version=version,
        schema_json=schema_json,
        content_hash=hash_json(schema_json),
    )
    return add_tool_schema_version(session, record)


def create_strategy(session: Session, *, name: str, workflow_type: str, strategy_id: str | None = None) -> Strategy:
    if workflow_type not in {"direct", "plan_execute", "react_reflection"}:
        raise ValueError("workflow_type must be one of direct/plan_execute/react_reflection")
    parent_id = strategy_id or f"strat-{new_id()}"
    if get_strategy(session, parent_id) is not None:
        raise ValueError("strategy already exists")
    return add_strategy(session, Strategy(id=parent_id, name=name, workflow_type=workflow_type))


def list_all_strategies(session: Session) -> list[Strategy]:
    return list_strategies(session)


def list_versions_for_strategy(session: Session, strategy_id: str) -> list[StrategyVersion]:
    if get_strategy(session, strategy_id) is None:
        raise ValueError("strategy not found")
    return list_strategy_versions_for_strategy(session, strategy_id)


def create_strategy_version(
    session: Session,
    *,
    strategy_id: str,
    name: str,
    version: str,
    prompt_version_id: str,
    tool_schema_version_id: str,
    model_provider: str = "mock",
    model_name: str = "mock-1",
    model_params: dict | None = None,
    temperature: float | None = None,
    allow_reflection: bool = False,
    max_tool_calls: int = 12,
) -> StrategyVersion:
    # §7.3：创建 strategy version 必须绑定已存在的 prompt version 和 tool schema version。
    strategy = get_strategy(session, strategy_id)
    if strategy is None:
        raise ValueError("strategy not found")
    if get_prompt_version(session, prompt_version_id) is None:
        raise ValueError("prompt version not found")
    if get_tool_schema_version(session, tool_schema_version_id) is None:
        raise ValueError("tool schema version not found")
    version_id = f"sv-{new_id()}"
    if get_strategy_version(session, version_id) is not None:
        raise ValueError("strategy version id collision")
    record = StrategyVersion(
        id=version_id,
        strategy_id=strategy_id,
        name=name,
        version=version,
        workflow_type=strategy.workflow_type,
        model_provider=model_provider,
        model_name=model_name,
        model_params=model_params or {},
        temperature=temperature,
        allow_reflection=allow_reflection,
        max_tool_calls=max_tool_calls,
        prompt_version_id=prompt_version_id,
        tool_schema_version_id=tool_schema_version_id,
        prompt_ref=prompt_version_id,
        tool_schema_ref=tool_schema_version_id,
        is_locked=False,
    )
    return add_strategy_version(session, record)
