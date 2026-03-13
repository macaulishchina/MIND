"""System REST endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query, Request
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


@router.get("/system/status")
async def system_status(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    detailed: Annotated[bool, Query()] = False,
) -> JSONResponse:
    """Return system status, optionally with a full health report."""
    registry = get_registry(request)
    app_req = build_app_request(request, principal)
    if detailed:
        from mind.kernel.health import compute_health_report

        report = compute_health_report(registry.store)
        response = registry.system_status_service.health(app_req)
        if response.result is not None:
            response.result["health_report"] = report.to_dict()
        return app_json_response(response)
    return app_json_response(registry.system_status_service.health(app_req))
