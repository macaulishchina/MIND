"""Offline job REST endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import JSONResponse

from mind.api._utils import app_json_response, build_app_request, get_registry
from mind.api.auth import require_api_key
from mind.api.pagination import parse_pagination
from mind.app.context import PrincipalContext

router = APIRouter(prefix="/v1", tags=["jobs"])
PayloadBody = Annotated[dict[str, Any] | None, Body()]
StatusFilterQuery = Annotated[list[str] | None, Query(alias="status")]


@router.post("/jobs")
async def submit_job(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).offline_job_app_service.submit_job(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.post("/jobs/enqueue")
async def enqueue_job(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    """Enqueue an offline maintenance job (alias for POST /jobs with explicit intent)."""
    response = get_registry(request).offline_job_app_service.submit_job(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
) -> JSONResponse:
    response = get_registry(request).offline_job_app_service.get_job(
        build_app_request(request, principal, input_overrides={"job_id": job_id})
    )
    return app_json_response(response)


@router.get("/jobs")
async def list_jobs(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    status_filter: StatusFilterQuery = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    limit_value, offset_value = parse_pagination(limit, offset)
    response = get_registry(request).offline_job_app_service.list_jobs(
        build_app_request(
            request,
            principal,
            input_overrides={
                "limit": limit_value,
                "offset": offset_value,
                "statuses": status_filter or [],
            },
        )
    )
    return app_json_response(response)


@router.delete("/jobs/{job_id}")
async def cancel_job(
    job_id: str,
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
) -> JSONResponse:
    response = get_registry(request).offline_job_app_service.cancel_job(
        build_app_request(request, principal, input_overrides={"job_id": job_id})
    )
    return app_json_response(response)
