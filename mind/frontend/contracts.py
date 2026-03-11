"""Frontend-facing contracts frozen for Phase M prework."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mind.telemetry import TelemetryEventKind, TelemetryScope


class FrontendModel(BaseModel):
    """Strict base model for frontend-facing contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class FrontendDebugTimelineQuery(FrontendModel):
    """Frozen frontend-facing query for debug timeline retrieval."""

    run_id: str | None = None
    operation_id: str | None = None
    job_id: str | None = None
    workspace_id: str | None = None
    object_id: str | None = None
    scopes: list[TelemetryScope] = Field(default_factory=list)
    event_kinds: list[TelemetryEventKind] = Field(default_factory=list)
    limit: int = Field(default=200, ge=1, le=500)
    include_payload: bool = False
    include_debug_fields: bool = False
    include_state_deltas: bool = True

    @model_validator(mode="after")
    def enforce_selector(self) -> FrontendDebugTimelineQuery:
        has_filter = any(
            (
                self.run_id,
                self.operation_id,
                self.job_id,
                self.workspace_id,
                self.object_id,
                self.scopes,
                self.event_kinds,
            )
        )
        if not has_filter:
            raise ValueError("frontend debug timeline queries require at least one filter")
        return self


class FrontendDebugTimelineEvent(FrontendModel):
    """Timeline item returned to frontend debug surfaces."""

    event_id: str = Field(min_length=1)
    parent_event_id: str | None = None
    occurred_at: datetime
    scope: TelemetryScope
    kind: TelemetryEventKind
    run_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    job_id: str | None = None
    workspace_id: str | None = None
    object_id: str | None = None
    object_version: int | None = Field(default=None, ge=1)
    label: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    payload: dict[str, Any] | None = None
    debug_fields: dict[str, Any] | None = None


class FrontendObjectDeltaView(FrontendModel):
    """Stable frontend view for object delta inspection."""

    event_id: str = Field(min_length=1)
    occurred_at: datetime
    object_id: str = Field(min_length=1)
    object_version: int = Field(ge=1)
    summary: str = Field(min_length=1)
    before: dict[str, Any]
    after: dict[str, Any]
    delta: dict[str, Any]


class FrontendDebugContextView(FrontendModel):
    """Stable frontend view for context selection and access shaping."""

    event_id: str = Field(min_length=1)
    occurred_at: datetime
    operation_id: str = Field(min_length=1)
    workspace_id: str | None = None
    context_kind: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    candidate_ids: list[str] = Field(default_factory=list)
    selected_object_ids: list[str] = Field(default_factory=list)
    context_object_ids: list[str] = Field(default_factory=list)
    verification_notes: list[str] = Field(default_factory=list)


class FrontendDebugEvidenceView(FrontendModel):
    """Stable frontend view for retrieval/workspace evidence support."""

    event_id: str = Field(min_length=1)
    occurred_at: datetime
    operation_id: str = Field(min_length=1)
    workspace_id: str | None = None
    object_id: str = Field(min_length=1)
    object_type: str | None = None
    summary: str = Field(min_length=1)
    selected: bool = False
    score: float | None = None
    priority: float | None = None
    reason_selected: str | None = None
    content_preview: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


class FrontendDebugTimelineResponse(FrontendModel):
    """Frontend-facing debug timeline payload."""

    query: FrontendDebugTimelineQuery
    total_event_count: int = Field(ge=0)
    matched_event_count: int = Field(ge=0)
    returned_event_count: int = Field(ge=0)
    available_scopes: list[TelemetryScope] = Field(default_factory=list)
    timeline: list[FrontendDebugTimelineEvent] = Field(default_factory=list)
    object_deltas: list[FrontendObjectDeltaView] = Field(default_factory=list)
    context_views: list[FrontendDebugContextView] = Field(default_factory=list)
    evidence_views: list[FrontendDebugEvidenceView] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_counts(self) -> FrontendDebugTimelineResponse:
        if self.returned_event_count != len(self.timeline):
            raise ValueError("returned_event_count must match timeline length")
        if self.returned_event_count > self.matched_event_count:
            raise ValueError("returned_event_count cannot exceed matched_event_count")
        return self
