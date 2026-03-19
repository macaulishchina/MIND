"""Frontend surface REST endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse

from mind.api._utils import app_json_response, build_app_request, get_registry
from mind.api.auth import require_api_key
from mind.app._service_utils import new_response
from mind.app.context import PrincipalContext
from mind.app.contracts import AppError, AppErrorCode, AppStatus
from mind.frontend import build_frontend_experience_catalog

router = APIRouter(prefix="/v1", tags=["frontend"])
PayloadBody = Annotated[dict[str, Any] | None, Body()]


@router.get("/frontend/catalog")
async def frontend_catalog(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
) -> JSONResponse:
    app_request = build_app_request(request, principal)
    response = new_response(app_request)
    response.status = AppStatus.OK
    response.result = build_frontend_experience_catalog().model_dump(mode="json")
    return app_json_response(response)


@router.get("/frontend/gate-demo")
async def frontend_gate_demo(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
) -> JSONResponse:
    response = get_registry(request).frontend_experience_service.gate_demo(
        build_app_request(request, principal)
    )
    return app_json_response(response)


@router.post("/frontend/ingest")
async def frontend_ingest(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).frontend_experience_service.ingest(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.post("/frontend/retrieve")
async def frontend_retrieve(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).frontend_experience_service.retrieve(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.post("/frontend/access")
async def frontend_access(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).frontend_experience_service.access(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.post("/frontend/offline")
async def frontend_offline(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).frontend_experience_service.submit_offline(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.post("/frontend/benchmark:run")
async def frontend_benchmark_run(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).frontend_experience_service.run_memory_lifecycle_benchmark(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.get("/frontend/benchmark:workspace")
async def frontend_benchmark_workspace(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
) -> JSONResponse:
    response = (
        get_registry(request).frontend_experience_service.load_memory_lifecycle_benchmark_workspace(
            build_app_request(request, principal)
        )
    )
    return app_json_response(response)


@router.post("/frontend/benchmark:report")
async def frontend_benchmark_report(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(
        request
    ).frontend_experience_service.load_memory_lifecycle_benchmark_report(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.post("/frontend/benchmark:slice:generate")
async def frontend_benchmark_slice_generate(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(
        request
    ).frontend_experience_service.generate_memory_lifecycle_benchmark_slice(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.get("/frontend/settings")
async def frontend_settings(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
) -> JSONResponse:
    response = get_registry(request).frontend_settings_service.get_page(
        build_app_request(request, principal)
    )
    return app_json_response(response)


@router.post("/frontend/settings:preview")
async def frontend_settings_preview(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).frontend_settings_service.preview(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.post("/frontend/settings:apply")
async def frontend_settings_apply(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).frontend_settings_service.apply(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.post("/frontend/llm/services:upsert")
async def frontend_llm_service_upsert(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).frontend_settings_service.upsert_llm_service(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.post("/frontend/llm/services:discover-models")
async def frontend_llm_service_discover_models(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).frontend_settings_service.discover_llm_models(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.post("/frontend/llm/services:activate")
async def frontend_llm_service_activate(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).frontend_settings_service.activate_llm_service(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.post("/frontend/llm/services:delete")
async def frontend_llm_service_delete(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).frontend_settings_service.delete_llm_service(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.post("/frontend/settings:restore")
async def frontend_settings_restore(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    response = get_registry(request).frontend_settings_service.restore(
        build_app_request(request, principal, payload=payload)
    )
    return app_json_response(response)


@router.get("/frontend/debug:workspace")
async def frontend_debug_workspace(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
) -> JSONResponse:
    registry = get_registry(request)
    app_request = build_app_request(request, principal)

    try:
        result = registry.frontend_debug_service.load_workspace()
    except RuntimeError as exc:
        response = new_response(app_request)
        response.status = AppStatus.ERROR
        response.error = AppError(
            code=AppErrorCode.UNSUPPORTED_OPERATION,
            message=str(exc),
        )
        return app_json_response(response)

    response = new_response(app_request)
    response.status = AppStatus.OK
    response.result = result.model_dump(mode="json")
    return app_json_response(response)


@router.post("/frontend/debug:timeline")
async def frontend_debug_timeline(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_api_key)],
    payload: PayloadBody = None,
) -> JSONResponse:
    registry = get_registry(request)
    app_request = build_app_request(request, principal, payload=payload)

    try:
        result = registry.frontend_debug_service.query_timeline(app_request.input)
    except RuntimeError as exc:
        response = new_response(app_request)
        response.status = AppStatus.ERROR
        response.error = AppError(
            code=AppErrorCode.UNSUPPORTED_OPERATION,
            message=str(exc),
        )
        return app_json_response(response)

    response = new_response(app_request)
    response.status = AppStatus.OK
    response.result = result.model_dump(mode="json")
    return app_json_response(response)
