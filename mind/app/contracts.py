"""Unified request/response envelope for the Application Service Layer."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import Field

from mind.app.context import (
    ExecutionPolicy,
    NamespaceContext,
    PrincipalContext,
    SessionContext,
)
from mind.primitives.contracts import ContractModel

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
