"""Internal REST request/response helpers."""

from __future__ import annotations

from typing import Any, TypeVar
from uuid import uuid4

from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from mind.app import (
    AppError,
    AppErrorCode,
    AppRequest,
    AppResponse,
    AppServiceError,
    AppStatus,
    ExecutionPolicy,
    NamespaceContext,
    PrincipalContext,
    SessionContext,
    SourceChannel,
)
from mind.app.registry import AppServiceRegistry

T = TypeVar("T", bound=BaseModel)

_APP_ENVELOPE_KEYS = frozenset(
    {
        "idempotency_key",
        "input",
        "namespace",
        "policy",
        "principal",
        "session",
    }
)

_ERROR_STATUS_CODES: dict[AppErrorCode, int] = {
    AppErrorCode.ACCESS_SERVICE_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
    AppErrorCode.AUTHORIZATION_ERROR: status.HTTP_401_UNAUTHORIZED,
    AppErrorCode.BUDGET_EXHAUSTED: status.HTTP_403_FORBIDDEN,
    AppErrorCode.CAPABILITY_REQUIRED: status.HTTP_403_FORBIDDEN,
    AppErrorCode.CONFLICT: status.HTTP_409_CONFLICT,
    AppErrorCode.GOVERNANCE_EXECUTION_FAILED: status.HTTP_500_INTERNAL_SERVER_ERROR,
    AppErrorCode.INTERNAL_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
    AppErrorCode.NOT_FOUND: status.HTTP_404_NOT_FOUND,
    AppErrorCode.OBJECT_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    AppErrorCode.OFFLINE_MAINTENANCE_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
    AppErrorCode.STORE_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
    AppErrorCode.UNSUPPORTED_OPERATION: status.HTTP_400_BAD_REQUEST,
    AppErrorCode.VALIDATION_ERROR: status.HTTP_400_BAD_REQUEST,
}


def get_registry(request: Request) -> AppServiceRegistry:
    """Return the current app service registry from application state."""

    return request.app.state.registry


def build_app_request(
    request: Request,
    principal: PrincipalContext,
    *,
    payload: dict[str, Any] | None = None,
    input_overrides: dict[str, Any] | None = None,
) -> AppRequest:
    """Project HTTP request state into the shared app-layer envelope."""

    raw_payload = dict(payload or {})
    request_id = getattr(request.state, "request_id", f"req-{uuid4().hex[:16]}")
    raw_input = (
        dict(raw_payload["input"])
        if isinstance(raw_payload.get("input"), dict)
        else {key: value for key, value in raw_payload.items() if key not in _APP_ENVELOPE_KEYS}
    )
    if input_overrides:
        raw_input.update(input_overrides)

    namespace = _model_or_none(NamespaceContext, raw_payload.get("namespace"))
    policy = _model_or_none(ExecutionPolicy, raw_payload.get("policy"))
    session = _build_session_context(request, raw_payload, request_id=request_id)
    idempotency_key = raw_payload.get("idempotency_key") or request.headers.get(
        "X-Idempotency-Key"
    )

    return AppRequest(
        request_id=request_id,
        idempotency_key=idempotency_key,
        principal=principal,
        namespace=namespace,
        session=session,
        policy=policy,
        input=raw_input,
    )


def app_json_response(response: AppResponse) -> JSONResponse:
    """Render an app-layer envelope with the correct HTTP status code."""

    return JSONResponse(
        status_code=http_status_from_app(response),
        content=response.model_dump(mode="json"),
    )


def app_service_error_response(
    request: Request,
    exc: AppServiceError,
) -> JSONResponse:
    """Render a structured error envelope for app-layer exceptions."""

    request_id = getattr(request.state, "request_id", f"req-{uuid4().hex[:16]}")
    app_status = _status_from_error_code(exc.code)
    response = AppResponse(
        status=app_status,
        error=AppError(code=exc.code, message=str(exc)),
        request_id=request_id,
        trace_ref=f"app:{request_id}",
    )
    return app_json_response(response)


def validation_error_response(
    request: Request,
    *,
    errors: list[dict[str, Any]],
) -> JSONResponse:
    """Render a consistent validation failure response."""

    request_id = getattr(request.state, "request_id", f"req-{uuid4().hex[:16]}")
    response = AppResponse(
        status=AppStatus.ERROR,
        error=AppError(
            code=AppErrorCode.VALIDATION_ERROR,
            message="request validation failed",
            details={"errors": errors},
        ),
        request_id=request_id,
        trace_ref=f"app:{request_id}",
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=response.model_dump(mode="json"),
    )


def unexpected_error_response(request: Request, exc: Exception) -> JSONResponse:
    """Render an internal error envelope for uncaught exceptions."""

    request_id = getattr(request.state, "request_id", f"req-{uuid4().hex[:16]}")
    response = AppResponse(
        status=AppStatus.ERROR,
        error=AppError(code=AppErrorCode.INTERNAL_ERROR, message=str(exc)),
        request_id=request_id,
        trace_ref=f"app:{request_id}",
    )
    return app_json_response(response)


def http_status_from_app(response: AppResponse) -> int:
    """Map an app-layer response envelope to an HTTP status code."""

    if response.status is AppStatus.OK:
        return status.HTTP_200_OK
    if response.status is AppStatus.NOT_FOUND:
        return status.HTTP_404_NOT_FOUND
    if response.status is AppStatus.UNAUTHORIZED:
        return status.HTTP_401_UNAUTHORIZED
    if response.status is AppStatus.REJECTED:
        return status.HTTP_403_FORBIDDEN
    if response.error is None:
        return status.HTTP_503_SERVICE_UNAVAILABLE
    return _ERROR_STATUS_CODES.get(response.error.code, status.HTTP_400_BAD_REQUEST)


def _build_session_context(
    request: Request,
    payload: dict[str, Any],
    *,
    request_id: str,
) -> SessionContext:
    session_payload = (
        dict(payload.get("session", {}))
        if isinstance(payload.get("session"), dict)
        else {}
    )
    header_mapping = {
        "session_id": request.headers.get("X-Session-ID"),
        "conversation_id": request.headers.get("X-Conversation-ID"),
        "client_id": request.headers.get("X-Client-ID"),
        "device_id": request.headers.get("X-Device-ID"),
    }
    for key, value in header_mapping.items():
        if value is not None:
            session_payload.setdefault(key, value)
    session_payload.setdefault("session_id", f"rest-{request_id}")
    session_payload.setdefault("channel", SourceChannel.REST)
    session_payload.setdefault("request_id", request_id)
    return SessionContext.model_validate(session_payload)


def _model_or_none(model_type: type[T], payload: Any) -> T | None:
    if payload is None:
        return None
    return model_type.model_validate(payload)


def _status_from_error_code(code: AppErrorCode) -> AppStatus:
    if code is AppErrorCode.NOT_FOUND:
        return AppStatus.NOT_FOUND
    if code is AppErrorCode.AUTHORIZATION_ERROR:
        return AppStatus.UNAUTHORIZED
    return AppStatus.ERROR
