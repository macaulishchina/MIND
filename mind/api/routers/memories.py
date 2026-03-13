"""Memory REST endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import JSONResponse

from mind.api._utils import app_json_response, build_app_request, get_registry
from mind.api.auth import require_api_key
from mind.api.pagination import parse_pagination
from mind.app.context import PrincipalContext

router = APIRouter(prefix="/v1", tags=["memories"])
PayloadBody = Annotated[dict[str, Any] | None, Body()]


@router.post("/memories")
async def remember(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).memory_ingest_service.remember(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.get("/memories/{memory_id}")
async def get_memory(
    memory_id: str,
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
) -> JSONResponse:
    response = get_registry(request).memory_query_service.get_memory(
        build_app_request(request, principal, input_overrides={"object_id": memory_id})
    )
    return app_json_response(response)


@router.get("/memories")
async def list_memories(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    episode_id: str | None = None,
    task_id: str | None = None,
    object_types: Annotated[list[str] | None, Query()] = None,
    statuses: Annotated[list[str] | None, Query()] = None,
) -> JSONResponse:
    limit_value, offset_value = parse_pagination(limit, offset)
    response = get_registry(request).memory_query_service.list_memories(
        build_app_request(
            request,
            principal,
            input_overrides={
                "episode_id": episode_id,
                "limit": limit_value,
                "offset": offset_value,
                "object_types": object_types or [],
                "statuses": statuses or [],
                "task_id": task_id,
            },
        )
    )
    return app_json_response(response)


@router.post("/memories:search")
async def search_memories(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).memory_query_service.search(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.post("/memories:recall")
async def recall_memories(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).memory_query_service.recall(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.post("/memories/feedback")
async def record_feedback(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).feedback_service.record_feedback(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)
