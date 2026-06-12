from fastapi import APIRouter

from app.api.routes.projects import router as projects_router
from app.api.routes.strategy_versions import router as strategy_versions_router
from app.api.routes.test_plans import router as test_plans_router
from app.api.routes.test_runs import router as test_runs_router

api_router = APIRouter()
api_router.include_router(projects_router)
api_router.include_router(test_plans_router)
api_router.include_router(strategy_versions_router)
api_router.include_router(test_runs_router)
