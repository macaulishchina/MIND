"""Access REST endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse

from mind.api._utils import app_json_response, build_app_request, get_registry
from mind.api.auth import require_api_key
from mind.app.context import PrincipalContext

router = APIRouter(prefix="/v1", tags=["access"])
PayloadBody = Annotated[dict[str, Any] | None, Body()]


@router.post("/access:ask")
async def ask_access(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).memory_access_service.ask(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.post("/access:run")
async def run_access(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).memory_access_service.run_access(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.post("/access:explain")
async def explain_access(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).memory_access_service.explain_access(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)
