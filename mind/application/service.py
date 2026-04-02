"""Maintained application-layer entrypoint for adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

from mind import __version__
from mind.application.errors import ChatModelProfileError, MemoryNotFoundError
from mind.application.models import (
    CapabilitiesDto,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    ChatModelsResponse,
    ChatModelProfileDto,
    HistoryDto,
    IngestConversationRequest,
    ListMemoriesRequest,
    MemoriesResponse,
    HistoryResponse,
    MemoryDto,
    OwnerSelector,
    SearchMemoriesRequest,
    UpdateMemoryRequest,
)
from mind.config import ConfigManager, MemoryConfig
from mind.config.schema import ChatProfileConfig
from mind.llms.factory import LlmFactory
from mind.memory import Memory


class MindService:
    """Thin maintained service layer above the memory kernel."""

    def __init__(
        self,
        memory: Optional[Memory] = None,
        config: Optional[MemoryConfig] = None,
        toml_path: Optional[Union[str, Path]] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> None:
        resolved_config = config
        if resolved_config is None and memory is not None:
            resolved_config = getattr(memory, "_config", None)
        if resolved_config is None:
            resolved_config = ConfigManager(toml_path=toml_path).get(overrides=overrides)

        self._config = resolved_config
        self._memory = memory or Memory(config=resolved_config)
        self._chat_llms: Dict[str, Any] = {}

    @staticmethod
    def _compat_user_id(owner: OwnerSelector) -> str:
        return owner.compatibility_user_id()

    def _chat_profile(self, profile_id: str) -> ChatProfileConfig:
        profile = self._config.chat.profiles.get(profile_id)
        if profile is None:
            raise ChatModelProfileError(profile_id)
        return profile

    def _chat_llm(self, profile_id: str):
        llm = self._chat_llms.get(profile_id)
        if llm is None:
            llm = LlmFactory.create(self._chat_profile(profile_id).llm)
            self._chat_llms[profile_id] = llm
        return llm

    def ingest_conversation(self, request: IngestConversationRequest) -> MemoriesResponse:
        items = self._memory.add(
            messages=[message.model_dump() for message in request.messages],
            owner=request.owner.to_owner_context(),
            session_id=request.session_id,
            metadata=request.metadata,
        )
        dto_items = [MemoryDto.from_item(item) for item in items]
        return MemoriesResponse(items=dto_items, count=len(dto_items))

    def search_memories(self, request: SearchMemoriesRequest) -> MemoriesResponse:
        items = self._memory.search(
            query=request.query,
            user_id=self._compat_user_id(request.owner),
            limit=request.limit,
        )
        dto_items = [MemoryDto.from_item(item) for item in items]
        return MemoriesResponse(items=dto_items, count=len(dto_items))

    def list_memories(self, request: ListMemoriesRequest) -> MemoriesResponse:
        items = self._memory.get_all(
            user_id=self._compat_user_id(request.owner),
            limit=request.limit,
        )
        dto_items = [MemoryDto.from_item(item) for item in items]
        return MemoriesResponse(items=dto_items, count=len(dto_items))

    def get_memory(self, memory_id: str) -> MemoryDto:
        item = self._memory.get(memory_id)
        if item is None:
            raise MemoryNotFoundError(memory_id)
        return MemoryDto.from_item(item)

    def update_memory(self, memory_id: str, request: UpdateMemoryRequest) -> MemoryDto:
        item = self._memory.update(memory_id, request.content)
        if item is None:
            raise MemoryNotFoundError(memory_id)
        return MemoryDto.from_item(item)

    def delete_memory(self, memory_id: str) -> None:
        if not self._memory.delete(memory_id):
            raise MemoryNotFoundError(memory_id)

    def get_memory_history(self, memory_id: str) -> HistoryResponse:
        self.get_memory(memory_id)
        records = self._memory.history(memory_id)
        items = [HistoryDto.from_record(record) for record in records]
        return HistoryResponse(items=items, count=len(items))

    def list_chat_models(self) -> ChatModelsResponse:
        default_profile_id = self._config.chat.default_profile_id
        items = [
            ChatModelProfileDto(
                id=profile.id,
                label=profile.label,
                provider=profile.llm.provider,
                model=profile.llm.model,
                temperature=profile.llm.temperature,
                timeout=profile.llm.timeout,
                is_default=(profile.id == default_profile_id),
            )
            for profile in self._config.chat.profiles.values()
        ]
        return ChatModelsResponse(items=items, count=len(items))

    def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        profile = self._chat_profile(request.model_profile_id)
        llm = self._chat_llm(request.model_profile_id)

        # Validate owner through the maintained canonical selector even though
        # the current chat path does not yet hydrate memory context.
        request.owner.compatibility_user_id()
        reply = llm.generate(
            messages=[message.model_dump() for message in request.messages],
            temperature=profile.llm.temperature,
        )
        return ChatCompletionResponse(
            message=ChatMessage(role="assistant", content=reply),
            model_profile_id=profile.id,
            provider=profile.llm.provider,
            model=profile.llm.model,
        )

    def get_capabilities(self) -> CapabilitiesDto:
        return CapabilitiesDto(
            version=__version__,
            application_entrypoint="mind.application.MindService",
            adapters={"rest": True, "mcp": False, "cli": False},
            operations=[
                "list_chat_models",
                "chat_completion",
                "ingest_conversation",
                "search_memories",
                "list_memories",
                "get_memory",
                "update_memory",
                "delete_memory",
                "get_memory_history",
            ],
            owner_selector_modes=["external_user_id", "anonymous_session_id"],
        )

    def close(self) -> None:
        self._memory.close()
