"""FastAPI application entry point for the product REST API."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from os import environ
from pathlib import Path
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError as PydanticValidationError

from mind import __version__
from mind.api._utils import (
    app_service_error_response,
    unexpected_error_response,
    validation_error_response,
)
from mind.api.routers import (
    access_router,
    frontend_router,
    governance_router,
    jobs_router,
    memories_router,
    sessions_router,
    system_router,
    users_router,
)
from mind.app.errors import AppServiceError
from mind.app.registry import build_app_registry
from mind.cli_config import ResolvedCliConfig


def create_app(config: ResolvedCliConfig | None = None) -> FastAPI:
    """Build the FastAPI application and wire the shared app registry."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with build_app_registry(config) as registry:
            app.state.registry = registry
            yield

    app = FastAPI(title="MIND API", version=__version__, lifespan=lifespan)
    _install_middleware(app)
    _install_exception_handlers(app)
    app.include_router(memories_router)
    app.include_router(access_router)
    app.include_router(frontend_router)
    app.include_router(governance_router)
    app.include_router(jobs_router)
    app.include_router(sessions_router)
    app.include_router(users_router)
    app.include_router(system_router)
    _install_frontend_mount(app)
    return app


def run_server() -> None:
    """Run the FastAPI app with uvicorn."""

    port = int(environ.get("PORT", "18600"))
    uvicorn.run(
        "mind.api.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=port,
    )


def _install_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or f"http-{uuid4().hex[:16]}"
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def _install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppServiceError)
    async def handle_app_service_error(
        request: Request,
        exc: AppServiceError,
    ) -> JSONResponse:
        return app_service_error_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return validation_error_response(
            request,
            errors=[dict(error) for error in exc.errors()],
        )

    @app.exception_handler(PydanticValidationError)
    async def handle_pydantic_validation_error(
        request: Request,
        exc: PydanticValidationError,
    ) -> JSONResponse:
        return validation_error_response(
            request,
            errors=[dict(error) for error in exc.errors()],
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return unexpected_error_response(request, exc)


def _install_frontend_mount(app: FastAPI) -> None:
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
    if frontend_dir.exists():
        app.mount("/frontend", StaticFiles(directory=frontend_dir, html=True), name="frontend")
