from __future__ import annotations

import hashlib
import json

from app.agents.prompts import prompt_bundle
from app.agents.seeds import seed_list
from app.models.strategy import StrategyVersion
from app.models.versioning import PromptVersion, Strategy, ToolSchemaVersion
from app.repositories.strategies import get_strategy_version
from app.repositories.versioning import get_prompt_version, get_strategy, get_tool_schema_version
from app.tools import default_registry
from sqlalchemy.orm import Session


def _prompt_version_id_for(spec) -> str:
    return f"pv-{spec.prompt_ref}"


def _tool_schema_version_id_for(spec) -> str:
    return f"tsv-{spec.tool_schema_ref}"


def _strategy_parent_id_for(spec) -> str:
    return spec.workflow_type


def _tool_schema_payload() -> dict:
    registry = default_registry()
    tools: list[dict] = []
    for name in sorted(registry.names()):
        spec = registry.get(name)
        tools.append(
            {
                "name": name,
                "input_schema": spec.input_model.model_json_schema(),
                "output_schema": spec.output_model.model_json_schema(),
            }
        )
    return {"version": "v1", "tools": tools}


def _hash_json(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def seed_strategy_versions(session: Session) -> None:
    tool_schema_payload = _tool_schema_payload()
    tool_schema_id = None
    for spec in seed_list():
        strategy_parent_id = _strategy_parent_id_for(spec)
        if get_strategy(session, strategy_parent_id) is None:
            session.add(Strategy(id=strategy_parent_id, name=spec.name, workflow_type=spec.workflow_type))

        prompt_payload = prompt_bundle(spec)
        prompt_version_id = _prompt_version_id_for(spec)
        prompt_hash = _hash_json(prompt_payload)
        prompt_version = get_prompt_version(session, prompt_version_id)
        if prompt_version is None:
            session.add(
                PromptVersion(
                    id=prompt_version_id,
                    name=f"{spec.name} Prompt",
                    version="v1",
                    content=prompt_payload,
                    content_hash=prompt_hash,
                    source_ref=spec.prompt_ref,
                )
            )
        elif prompt_version.content_hash != prompt_hash:
            prompt_version.name = f"{spec.name} Prompt"
            prompt_version.version = "v1"
            prompt_version.content = prompt_payload
            prompt_version.content_hash = prompt_hash
            prompt_version.source_ref = spec.prompt_ref
            session.add(prompt_version)

        tool_schema_id = _tool_schema_version_id_for(spec)
        tool_schema_hash = _hash_json(tool_schema_payload)
        tool_schema_version = get_tool_schema_version(session, tool_schema_id)
        if tool_schema_version is None:
            session.add(
                ToolSchemaVersion(
                    id=tool_schema_id,
                    version="v1",
                    schema_json=tool_schema_payload,
                    content_hash=tool_schema_hash,
                )
            )
        elif tool_schema_version.content_hash != tool_schema_hash:
            tool_schema_version.version = "v1"
            tool_schema_version.schema_json = tool_schema_payload
            tool_schema_version.content_hash = tool_schema_hash
            session.add(tool_schema_version)

        existing = get_strategy_version(session, spec.id)
        if existing is not None:
            # 老库里 V1 三条 strategy_version 早已存在，但 stage1 新增的版本外键是空的。
            # 不能直接 continue 跳过，否则升级后这些行 strategy_id/prompt_version_id/
            # tool_schema_version_id/version 永远是 NULL，新 run 进 _strategy_snapshot()
            # 找不到 prompt/tool version 就直接失败。这里对已有行做缺失字段回填。
            if existing.strategy_id is None:
                existing.strategy_id = strategy_parent_id
            if not existing.version:
                existing.version = "v1"
            if existing.prompt_version_id is None:
                existing.prompt_version_id = prompt_version_id
            if existing.tool_schema_version_id is None:
                existing.tool_schema_version_id = tool_schema_id
            session.add(existing)
            continue
        session.add(
            StrategyVersion(
                id=spec.id,
                strategy_id=strategy_parent_id,
                name=spec.name,
                version="v1",
                workflow_type=spec.workflow_type,
                model_provider=spec.model_provider,
                model_name=spec.model_name,
                model_params=spec.model_params,
                temperature=spec.temperature,
                allow_reflection=spec.allow_reflection,
                max_tool_calls=spec.max_tool_calls,
                prompt_version_id=prompt_version_id,
                tool_schema_version_id=tool_schema_id,
                prompt_ref=spec.prompt_ref,
                tool_schema_ref=spec.tool_schema_ref,
                is_locked=False,
            )
        )
    session.commit()
