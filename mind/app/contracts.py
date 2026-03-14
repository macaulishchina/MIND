"""Unified request/response envelope for the Application Service Layer."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mind.app.context import (
    ExecutionPolicy,
    NamespaceContext,
    PrincipalContext,
    ProviderSelection,
    SessionContext,
)
from mind.primitives.contracts import ContractModel
from mind.telemetry import TelemetryEventKind, TelemetryScope

# ---------------------------------------------------------------------------
# Frontend model base
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Status and error enums
# ---------------------------------------------------------------------------


class AppStatus(StrEnum):
    """Top-level status returned in every AppResponse."""

    OK = "ok"
    ERROR = "error"
    REJECTED = "rejected"
    NOT_FOUND = "not_found"
    UNAUTHORIZED = "unauthorized"


class AppErrorCode(StrEnum):
    """Unified error codes spanning all domain layers."""

    # Primitive-origin
    CAPABILITY_REQUIRED = "capability_required"
    BUDGET_EXHAUSTED = "budget_exhausted"
    EMPTY_INPUT_REFS = "empty_input_refs"
    EPISODE_MISSING = "episode_missing"
    EVIDENCE_MISSING = "evidence_missing"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    INTERNAL_ERROR = "internal_error"
    INVALID_CONTENT = "invalid_content"
    INVALID_OBJECT_TYPE = "invalid_object_type"
    INVALID_REFS = "invalid_refs"
    INVALID_STATUS = "invalid_status"
    LINK_CYCLE = "link_cycle"
    MISSING_CONTEXT = "missing_context"
    MISSING_EPISODE_CONTEXT = "missing_episode_context"
    MISSING_SOURCE_REFS = "missing_source_refs"
    OBJECT_INACCESSIBLE = "object_inaccessible"
    OBJECT_NOT_FOUND = "object_not_found"
    REFLECTION_VALIDATION_FAILED = "reflection_validation_failed"
    RETRIEVAL_BACKEND_UNAVAILABLE = "retrieval_backend_unavailable"
    ROLLBACK_FAILED = "rollback_failed"
    SCHEMA_INVALID = "schema_invalid"
    SCHEMA_VIOLATION = "schema_violation"
    SELF_LINK_NOT_ALLOWED = "self_link_not_allowed"
    SCOPE_EMPTY = "scope_empty"
    SOURCE_REF_NOT_FOUND = "source_ref_not_found"
    SUMMARY_VALIDATION_FAILED = "summary_validation_failed"
    UNSAFE_CONTENT = "unsafe_content"
    UNSAFE_STATE_TRANSITION = "unsafe_state_transition"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    UNSUPPORTED_QUERY_MODE = "unsupported_query_mode"
    UNSUPPORTED_SCOPE = "unsupported_scope"

    # Governance-origin
    GOVERNANCE_INVALID_STAGE = "governance_invalid_stage"
    GOVERNANCE_MISSING_AUDIT = "governance_missing_audit"
    GOVERNANCE_EXECUTION_FAILED = "governance_execution_failed"

    # Access-origin
    ACCESS_SERVICE_ERROR = "access_service_error"

    # Offline-origin
    OFFLINE_MAINTENANCE_ERROR = "offline_maintenance_error"

    # Store-origin
    STORE_ERROR = "store_error"

    # Validation / generic
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    AUTHORIZATION_ERROR = "authorization_error"
    CONFLICT = "conflict"


# ---------------------------------------------------------------------------
# Envelope models
# ---------------------------------------------------------------------------


class AppError(ContractModel):
    """Structured error payload returned inside AppResponse."""

    code: AppErrorCode
    message: str = Field(min_length=1)
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class AppRequest(ContractModel):
    """Unified inbound request envelope for all application services."""

    request_id: str = Field(default_factory=lambda: f"req-{uuid4().hex[:16]}")
    idempotency_key: str | None = None
    principal: PrincipalContext | None = None
    namespace: NamespaceContext | None = None
    session: SessionContext | None = None
    policy: ExecutionPolicy | None = None
    provider_selection: ProviderSelection | None = None
    input: dict[str, Any] = Field(default_factory=dict)  # noqa: A003


class AppResponse(ContractModel):
    """Unified outbound response envelope for all application services."""

    model_config = ContractModel.model_config.copy()
    model_config["frozen"] = False

    status: AppStatus = AppStatus.OK
    result: dict[str, Any] | None = None
    error: AppError | None = None
    trace_ref: str | None = None
    audit_ref: str | None = None
    request_id: str | None = None
    idempotency_key: str | None = None
