from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.repositories.strategies import get_strategy_version, list_strategy_versions

router = APIRouter(prefix="/api/v1/strategy-versions", tags=["strategy-versions"])


@router.get("")
def list_strategy_versions_route(db: Session = Depends(get_db)):
    # 返回系统内置的策略版本列表。V1 里这是只读种子数据，给前端做策略选择。
    return list_strategy_versions(db)


@router.get("/{version_id}")
def get_strategy_version_route(version_id: str, db: Session = Depends(get_db)):
    # 查询单个策略版本的快照配置，帮助前端展示 workflow / model / budget 默认值。
    strategy = get_strategy_version(db, version_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    return strategy
