from __future__ import annotations

from fastapi import APIRouter

from app.schemas.api_llm_options import LlmOptionsOut
from app.services.llm_options import get_llm_options

router = APIRouter(prefix="/api/v1/llm-options", tags=["llm-options"])


@router.get("", response_model=LlmOptionsOut)
def get_llm_options_route():
    return get_llm_options()
