"""Shared DTOs for maintained adapters."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mind.config.models import (
    FactFamily,
    MemoryItem,
    MemoryOperation,
    MemoryStatus,
    MemoryType,
    OwnerContext,
)


class OwnerSelector(BaseModel):
    """Canonical owner selector for upper interfaces."""

    model_config = ConfigDict(extra="forbid")

    external_user_id: Optional[str] = None
    anonymous_session_id: Optional[str] = None
    display_name: Optional[str] = None
    channel: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_identity_mode(self) -> "OwnerSelector":
        if bool(self.external_user_id) == bool(self.anonymous_session_id):
            raise ValueError(
                "Provide exactly one of external_user_id or anonymous_session_id"
            )
        return self

    def to_owner_context(self) -> OwnerContext:
        return OwnerContext(
            external_user_id=self.external_user_id,
            anonymous_session_id=self.anonymous_session_id,
            display_name=self.display_name,
            channel=self.channel,
            metadata=self.metadata,
        )

    def compatibility_user_id(self) -> str:
        return self.external_user_id or self.anonymous_session_id or ""


class ChatMessage(BaseModel):
    """Structured chat message for ingestion."""

    model_config = ConfigDict(extra="forbid")

    role: str = Field(min_length=1)
    content: str = Field(min_length=1)


class IngestConversationRequest(BaseModel):
    """Application-layer request for owner-centered ingestion."""

    model_config = ConfigDict(extra="forbid")

    owner: OwnerSelector
    messages: List[ChatMessage] = Field(min_length=1)
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChatCompletionRequest(BaseModel):
    """Application-layer request for interactive chat completion."""

    model_config = ConfigDict(extra="forbid")

    owner: OwnerSelector
    model_profile_id: str = Field(min_length=1)
    messages: List[ChatMessage] = Field(min_length=1)


class SearchMemoriesRequest(BaseModel):
    """Application-layer request for semantic memory search."""

    model_config = ConfigDict(extra="forbid")

    owner: OwnerSelector
    query: str = Field(min_length=1)
    limit: Optional[int] = Field(default=None, ge=1)


class ListMemoriesRequest(BaseModel):
    """Application-layer request for active memory listing."""

    model_config = ConfigDict(extra="forbid")

    owner: OwnerSelector
    limit: int = Field(default=100, ge=1)


class UpdateMemoryRequest(BaseModel):
    """Application-layer request for manual memory updates."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)


class MemoryDto(BaseModel):
    """Stable memory DTO for maintained adapters."""

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    owner_id: Optional[str] = None
    content: str
    hash: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    confidence: Optional[float] = None
    status: MemoryStatus = MemoryStatus.ACTIVE
    source_context: Optional[str] = None
    source_session_id: Optional[str] = None
    version_of: Optional[str] = None
    importance: Optional[float] = None
    type: Optional[MemoryType] = None
    subject_ref: Optional[str] = None
    fact_family: Optional[FactFamily] = None
    relation_type: Optional[str] = None
    field_key: Optional[str] = None
    field_value_json: Optional[Dict[str, Any]] = None
    canonical_text: Optional[str] = None
    raw_text: Optional[str] = None
    score: Optional[float] = None

    @classmethod
    def from_item(cls, item: MemoryItem) -> "MemoryDto":
        return cls(**item.model_dump())


class HistoryDto(BaseModel):
    """Stable history DTO for maintained adapters."""

    model_config = ConfigDict(extra="forbid")

    id: str
    memory_id: str
    user_id: str
    operation: MemoryOperation
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    timestamp: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_record(cls, record: Dict[str, Any]) -> "HistoryDto":
        return cls(**record)


class MemoriesResponse(BaseModel):
    """Collection response for memory DTOs."""

    model_config = ConfigDict(extra="forbid")

    items: List[MemoryDto]
    count: int


class HistoryResponse(BaseModel):
    """Collection response for memory history."""

    model_config = ConfigDict(extra="forbid")

    items: List[HistoryDto]
    count: int


class CapabilitiesDto(BaseModel):
    """Capabilities advertised by the maintained adapter layer."""

    model_config = ConfigDict(extra="forbid")

    version: str
    application_entrypoint: str
    adapters: Dict[str, bool]
    operations: List[str]
    owner_selector_modes: List[str]


class ChatModelProfileDto(BaseModel):
    """Curated chat model profile exposed to adapters."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    provider: str
    model: str
    temperature: float
    timeout: float
    is_default: bool = False


class ChatModelsResponse(BaseModel):
    """Collection response for curated chat model profiles."""

    model_config = ConfigDict(extra="forbid")

    items: List[ChatModelProfileDto]
    count: int


class ChatCompletionResponse(BaseModel):
    """Response envelope for one assistant turn."""

    model_config = ConfigDict(extra="forbid")

    message: ChatMessage
    model_profile_id: str
    provider: str
    model: str
