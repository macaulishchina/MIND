"""Governance REST endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse

from mind.api._utils import app_json_response, build_app_request, get_registry
from mind.api.auth import require_api_key
from mind.app.context import PrincipalContext

router = APIRouter(prefix="/v1", tags=["governance"])
PayloadBody = Annotated[dict[str, Any] | None, Body()]


@router.post("/governance:plan-conceal")
async def plan_conceal(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).governance_app_service.plan_conceal(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.post("/governance:preview")
async def preview_conceal(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).governance_app_service.preview_conceal(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.post("/governance:execute-conceal")
async def execute_conceal(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).governance_app_service.execute_conceal(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)
