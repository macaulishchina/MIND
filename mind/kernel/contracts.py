"""Kernel-level contract types shared across layers.

These types were extracted from ``mind.primitives.contracts`` so that the kernel
layer can reference them without an upward import.  The primitives module
re-exports every symbol for backward compatibility.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, NonNegativeFloat, model_validator

# ---------------------------------------------------------------------------
# Base model
# ---------------------------------------------------------------------------


class ContractModel(BaseModel):
    """Strict base model shared by primitive contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PrimitiveName(StrEnum):
    WRITE_RAW = "write_raw"
    READ = "read"
    RETRIEVE = "retrieve"
    SUMMARIZE = "summarize"
    LINK = "link"
    REFLECT = "reflect"
    REORGANIZE_SIMPLE = "reorganize_simple"
    RECORD_FEEDBACK = "record_feedback"


class PrimitiveOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class PrimitiveErrorCode(StrEnum):
    CAPABILITY_REQUIRED = "capability_required"
    BUDGET_EXHAUSTED = "budget_exhausted"
    EMPTY_INPUT_REFS = "empty_input_refs"
    EPISODE_MISSING = "episode_missing"
    EVIDENCE_MISSING = "evidence_missing"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    INTERNAL_ERROR = "internal_error"
    INVALID_REFS = "invalid_refs"
    MISSING_EPISODE_CONTEXT = "missing_episode_context"
    OBJECT_INACCESSIBLE = "object_inaccessible"
    OBJECT_NOT_FOUND = "object_not_found"
    REFLECTION_VALIDATION_FAILED = "reflection_validation_failed"
    RETRIEVAL_BACKEND_UNAVAILABLE = "retrieval_backend_unavailable"
    ROLLBACK_FAILED = "rollback_failed"
    SCHEMA_INVALID = "schema_invalid"
    SELF_LINK_NOT_ALLOWED = "self_link_not_allowed"
    SUMMARY_VALIDATION_FAILED = "summary_validation_failed"
    UNSAFE_STATE_TRANSITION = "unsafe_state_transition"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    UNSUPPORTED_QUERY_MODE = "unsupported_query_mode"
    UNSUPPORTED_SCOPE = "unsupported_scope"


class PrimitiveCostCategory(StrEnum):
    GENERATION = "generation"
    MAINTENANCE = "maintenance"
    READ = "read"
    RETRIEVAL = "retrieval"
    STORAGE = "storage"
    WRITE = "write"


class RetrieveQueryMode(StrEnum):
    KEYWORD = "keyword"
    TIME_WINDOW = "time_window"
    VECTOR = "vector"


# ---------------------------------------------------------------------------
# Small models needed by call-log / budget-event
# ---------------------------------------------------------------------------


class BudgetCost(ContractModel):
    category: PrimitiveCostCategory
    amount: NonNegativeFloat
    unit: str = Field(default="cost_units", min_length=1)


class PrimitiveError(ContractModel):
    code: PrimitiveErrorCode
    message: str = Field(min_length=1)
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Call log & budget event — consumed by MemoryStore protocol
# ---------------------------------------------------------------------------


class PrimitiveCallLog(ContractModel):
    call_id: str = Field(min_length=1)
    primitive: PrimitiveName
    actor: str = Field(min_length=1)
    timestamp: datetime
    target_ids: list[str] = Field(default_factory=list)
    cost: list[BudgetCost] = Field(default_factory=list)
    outcome: PrimitiveOutcome
    request: dict[str, Any]
    response: dict[str, Any] | None = None
    error: PrimitiveError | None = None

    @model_validator(mode="after")
    def enforce_log_shape(self) -> PrimitiveCallLog:
        if self.outcome is PrimitiveOutcome.SUCCESS:
            if self.response is None or self.error is not None:
                raise ValueError("successful log requires response and forbids error")
        else:
            if self.response is not None or self.error is None:
                raise ValueError("non-success log requires error and forbids response")
        return self


class BudgetEvent(ContractModel):
    event_id: str = Field(min_length=1)
    call_id: str = Field(min_length=1)
    scope_id: str = Field(min_length=1)
    primitive: PrimitiveName
    actor: str = Field(min_length=1)
    timestamp: datetime
    outcome: PrimitiveOutcome
    cost: list[BudgetCost] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
