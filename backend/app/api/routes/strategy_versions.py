from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.repositories.strategies import get_strategy_version
from app.schemas.api_strategy import StrategyVersionOut

router = APIRouter(prefix="/api/v1/strategy-versions", tags=["strategy-versions"])


@router.get("/{version_id}", response_model=StrategyVersionOut)
def get_strategy_version_route(version_id: str, db: Session = Depends(get_db)):
    # 查询单个策略版本的快照配置，帮助前端展示 workflow / model / budget 默认值。
    strategy = get_strategy_version(db, version_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    return strategy
