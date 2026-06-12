from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.api_plan import TestPlanCreateRequest
from app.services.test_plans import create_test_plan, get_test_plan_or_404

router = APIRouter(prefix="/api/v1/test-plans", tags=["test-plans"])


@router.post("")
def create_test_plan_route(body: TestPlanCreateRequest, db: Session = Depends(get_db)):
    # 创建测试计划。它描述“要测什么、预算多少、默认用什么策略”，
    # 是 run 的模板，而不是一次具体执行。
    try:
        return create_test_plan(
            db,
            project_id=body.project_id,
            name=body.name,
            target_scope=body.target_scope,
            goal=body.goal,
            budget=body.budget,
            output_options=body.output_options,
            default_strategy_version_id=body.default_strategy_version_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{plan_id}")
def get_test_plan_route(plan_id: str, db: Session = Depends(get_db)):
    # 查询单个测试计划详情，给 run 创建页或计划详情页使用。
    try:
        return get_test_plan_or_404(db, plan_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
