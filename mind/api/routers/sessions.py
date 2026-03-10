"""Session REST endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import JSONResponse

from mind.api._utils import app_json_response, build_app_request, get_registry
from mind.api.auth import require_api_key
from mind.app.context import PrincipalContext

router = APIRouter(prefix="/v1", tags=["sessions"])
PayloadBody = Annotated[dict[str, Any] | None, Body()]


@router.post("/sessions")
async def open_session(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).user_state_service.open_session(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
) -> JSONResponse:
    response = get_registry(request).user_state_service.get_session(
        build_app_request(request, principal, input_overrides={"session_id": session_id})
    )
    return app_json_response(response)


@router.get("/sessions")
async def list_sessions(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    principal_id: Annotated[str | None, Query()] = None,
) -> JSONResponse:
    response = get_registry(request).user_state_service.list_sessions(
        build_app_request(request, principal, input_overrides={"principal_id": principal_id})
    )
    return app_json_response(response)
