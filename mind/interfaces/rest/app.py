"""FastAPI adapter for the maintained application layer."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi.encoders import jsonable_encoder
from fastapi import Depends, FastAPI, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mind.application import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatModelProfileError,
    ChatModelsResponse,
    HistoryResponse,
    IngestConversationRequest,
    ListMemoriesRequest,
    MemoriesResponse,
    MemoryDto,
    MemoryNotFoundError,
    MindService,
    OwnerSelector,
    OwnerSelectorError,
    SearchMemoriesRequest,
    UpdateMemoryRequest,
)
from mind.config import ConfigManager, MemoryConfig


def _validation_payload(exc: RequestValidationError) -> dict[str, Any]:
    return {"detail": jsonable_encoder(exc.errors())}


def _owner_selector_from_query(
    external_user_id: Optional[str] = Query(default=None),
    anonymous_session_id: Optional[str] = Query(default=None),
) -> OwnerSelector:
    try:
        return OwnerSelector(
            external_user_id=external_user_id,
            anonymous_session_id=anonymous_session_id,
        )
    except Exception as exc:  # Pydantic raises wrapped ValidationError
        raise OwnerSelectorError(str(exc)) from exc


def create_app(
    config: Optional[MemoryConfig] = None,
    toml_path: Optional[str] = None,
    overrides: Optional[dict[str, Any]] = None,
) -> FastAPI:
    """Create the maintained REST adapter."""

    resolved_config = config
    if resolved_config is None:
        resolved_config = ConfigManager(toml_path=toml_path).get(overrides=overrides)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.mind_service = MindService(config=resolved_config)
        yield
        app.state.mind_service.close()

    app = FastAPI(
        title="MIND REST API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_config.rest.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(MemoryNotFoundError)
    async def _handle_not_found(_: Request, exc: MemoryNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )

    @app.exception_handler(OwnerSelectorError)
    async def _handle_owner_error(_: Request, exc: OwnerSelectorError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(exc)},
        )

    @app.exception_handler(ChatModelProfileError)
    async def _handle_chat_profile_error(
        _: Request,
        exc: ChatModelProfileError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(exc)},
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_validation_payload(exc),
        )

    def _service(request: Request) -> MindService:
        return request.app.state.mind_service

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/capabilities")
    def capabilities(service: MindService = Depends(_service)) -> dict[str, Any]:
        return service.get_capabilities().model_dump()

    @app.get("/api/v1/chat/models", response_model=ChatModelsResponse)
    def list_chat_models(service: MindService = Depends(_service)) -> ChatModelsResponse:
        return service.list_chat_models()

    @app.post("/api/v1/chat/completions", response_model=ChatCompletionResponse)
    def chat_completion(
        payload: ChatCompletionRequest,
        service: MindService = Depends(_service),
    ) -> ChatCompletionResponse:
        return service.chat_completion(payload)

    @app.post("/api/v1/ingestions", response_model=MemoriesResponse)
    def ingest(
        payload: IngestConversationRequest,
        service: MindService = Depends(_service),
    ) -> MemoriesResponse:
        return service.ingest_conversation(payload)

    @app.post("/api/v1/memories/search", response_model=MemoriesResponse)
    def search(
        payload: SearchMemoriesRequest,
        service: MindService = Depends(_service),
    ) -> MemoriesResponse:
        return service.search_memories(payload)

    @app.get("/api/v1/memories", response_model=MemoriesResponse)
    def list_memories(
        owner: OwnerSelector = Depends(_owner_selector_from_query),
        limit: int = Query(default=100, ge=1),
        service: MindService = Depends(_service),
    ) -> MemoriesResponse:
        return service.list_memories(ListMemoriesRequest(owner=owner, limit=limit))

    @app.get("/api/v1/memories/{memory_id}", response_model=MemoryDto)
    def get_memory(memory_id: str, service: MindService = Depends(_service)) -> MemoryDto:
        return service.get_memory(memory_id)

    @app.patch("/api/v1/memories/{memory_id}", response_model=MemoryDto)
    def update_memory(
        memory_id: str,
        payload: UpdateMemoryRequest,
        service: MindService = Depends(_service),
    ) -> MemoryDto:
        return service.update_memory(memory_id, payload)

    @app.delete("/api/v1/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_memory(
        memory_id: str,
        service: MindService = Depends(_service),
    ) -> Response:
        service.delete_memory(memory_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/v1/memories/{memory_id}/history", response_model=HistoryResponse)
    def get_history(
        memory_id: str,
        service: MindService = Depends(_service),
    ) -> HistoryResponse:
        return service.get_memory_history(memory_id)

    return app
