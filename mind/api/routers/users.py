"""User REST endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse

from mind.api._utils import app_json_response, build_app_request, get_registry
from mind.api.auth import require_api_key
from mind.app.context import PrincipalContext

router = APIRouter(prefix="/v1", tags=["users"])
PayloadBody = Annotated[dict[str, Any] | None, Body()]


@router.get("/users/{principal_id}")
async def get_user(
    principal_id: str,
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
) -> JSONResponse:
    response = get_registry(request).user_state_service.get_principal(
        build_app_request(request, principal, input_overrides={"principal_id": principal_id})
    )
    return app_json_response(response)


@router.patch("/users/{principal_id}/preferences")
async def update_user_preferences(
    principal_id: str,
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).user_state_service.update_user_preferences(
        build_app_request(
            request,
            principal,
            payload=payload,
            input_overrides={"principal_id": principal_id},
        )
    )
    return app_json_response(response)


@router.get("/users/{principal_id}/defaults")
async def get_runtime_defaults(
    principal_id: str,
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
) -> JSONResponse:
    response = get_registry(request).user_state_service.get_runtime_defaults(
        build_app_request(request, principal, input_overrides={"principal_id": principal_id})
    )
    return app_json_response(response)
