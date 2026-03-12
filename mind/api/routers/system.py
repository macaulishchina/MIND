"""System REST endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse

from mind.api._utils import app_json_response, build_app_request, get_registry
from mind.api.auth import require_api_key
from mind.app.context import PrincipalContext

router = APIRouter(prefix="/v1", tags=["system"])
PayloadBody = Annotated[dict[str, Any] | None, Body()]


@router.get("/system/health")
async def health(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
) -> JSONResponse:
    response = get_registry(request).system_status_service.health(
        build_app_request(request, principal)
    )
    return app_json_response(response)


@router.get("/system/readiness")
async def readiness(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
) -> JSONResponse:
    response = get_registry(request).system_status_service.readiness(
        build_app_request(request, principal)
    )
    return app_json_response(response)


@router.get("/system/config")
async def config_summary(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
) -> JSONResponse:
    response = get_registry(request).system_status_service.config_summary(
        build_app_request(request, principal)
    )
    return app_json_response(response)


@router.get("/system/provider-status")
async def provider_status(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
) -> JSONResponse:
    response = get_registry(request).system_status_service.provider_status(
        build_app_request(request, principal)
    )
    return app_json_response(response)


@router.post("/system/provider-status:resolve")
async def provider_status_resolve(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).system_status_service.provider_status(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)
