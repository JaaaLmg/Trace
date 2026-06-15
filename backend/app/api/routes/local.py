from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.schemas.api_local import DirectoryPickOut, DirectoryPickRequest
from app.services.local_dialogs import pick_directory

router = APIRouter(prefix="/api/v1/local", tags=["local"])

_LOCAL_CLIENTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _require_local_client(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in _LOCAL_CLIENTS:
        raise HTTPException(status_code=403, detail="local directory picker only accepts localhost requests")


@router.post("/directories/pick", response_model=DirectoryPickOut)
def pick_directory_route(body: DirectoryPickRequest, request: Request):
    _require_local_client(request)
    try:
        path = pick_directory(initial_path=body.initial_path, title=body.title)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return DirectoryPickOut(path=path, cancelled=path is None)
