"""Typed primitive request/response contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, NonNegativeFloat, model_validator

from mind.kernel.provenance import DirectProvenanceInput, ProvenanceSummary
from mind.kernel.schema import (
    CORE_OBJECT_TYPES,
    VALID_RECORD_KIND,
    VALID_STATUS,
    ensure_valid_object,
)


class ContractModel(BaseModel):
    """Strict base model shared by primitive contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class PrimitiveName(StrEnum):
    WRITE_RAW = "write_raw"
    READ = "read"
    RETRIEVE = "retrieve"
    SUMMARIZE = "summarize"
    LINK = "link"
    REFLECT = "reflect"
    REORGANIZE_SIMPLE = "reorganize_simple"


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


class Capability(StrEnum):
    MEMORY_READ = "memory_read"
    MEMORY_READ_WITH_PROVENANCE = "memory_read_with_provenance"
    GOVERNANCE_PLAN = "governance_plan"
    GOVERNANCE_EXECUTE = "governance_execute"
    GOVERNANCE_APPROVE_FULL_ERASE = "governance_approve_full_erase"


class RetrieveQueryMode(StrEnum):
    KEYWORD = "keyword"
    TIME_WINDOW = "time_window"
    VECTOR = "vector"


class ReorganizeOperation(StrEnum):
    ARCHIVE = "archive"
    DEPRECATE = "deprecate"
    REPRIORITIZE = "reprioritize"
    SYNTHESIZE_SCHEMA = "synthesize_schema"


class BudgetCost(ContractModel):
    category: PrimitiveCostCategory
    amount: NonNegativeFloat
    unit: str = Field(default="cost_units", min_length=1)


class BudgetConstraint(ContractModel):
    max_cost: NonNegativeFloat | None = None
    max_candidates: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def require_at_least_one_limit(self) -> BudgetConstraint:
        if self.max_cost is None and self.max_candidates is None:
            raise ValueError("budget constraint must define at least one limit")
        return self


class PrimitiveError(ContractModel):
    code: PrimitiveErrorCode
    message: str = Field(min_length=1)
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class PrimitiveExecutionContext(ContractModel):
    actor: str = Field(min_length=1)
    budget_scope_id: str = Field(default="global", min_length=1)
    budget_limit: NonNegativeFloat | None = None
    capabilities: list[Capability] = Field(default_factory=lambda: [Capability.MEMORY_READ])
    dev_mode: bool = False
    provider_selection: dict[str, Any] | None = None
    telemetry_run_id: str | None = None
    telemetry_operation_id: str | None = None
    telemetry_parent_event_id: str | None = None


class MemoryObject(ContractModel):
    id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    content: str | dict[str, Any]
    source_refs: list[str]
    created_at: str
    updated_at: str
    version: int = Field(ge=1)
    status: str = Field(min_length=1)
    priority: float = Field(ge=0, le=1)
    metadata: dict[str, Any]

    @model_validator(mode="after")
    def enforce_frozen_object_contract(self) -> MemoryObject:
        if self.type not in CORE_OBJECT_TYPES:
            raise ValueError(f"unsupported object type '{self.type}'")
        if self.status not in VALID_STATUS:
            raise ValueError(f"unsupported object status '{self.status}'")
        ensure_valid_object(self.model_dump())
        return self


class WriteRawRequest(ContractModel):
    record_kind: str = Field(min_length=1)
    content: str | dict[str, Any]
    episode_id: str = Field(min_length=1)
    timestamp_order: int = Field(ge=1)
    direct_provenance: DirectProvenanceInput | None = None

    @model_validator(mode="after")
    def enforce_record_kind(self) -> WriteRawRequest:
        if self.record_kind not in VALID_RECORD_KIND:
            raise ValueError(f"unsupported record_kind '{self.record_kind}'")
        return self


class WriteRawResponse(ContractModel):
    object_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    provenance_id: str | None = None


class ReadRequest(ContractModel):
    object_ids: list[str] = Field(min_length=1)
    include_provenance: bool = False


class ReadResponse(ContractModel):
    objects: list[MemoryObject] = Field(min_length=1)
    provenance_summaries: dict[str, ProvenanceSummary] = Field(default_factory=dict)


class RetrieveFilters(ContractModel):
    episode_id: str | None = None
    object_types: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    task_id: str | None = None

    @model_validator(mode="after")
    def enforce_known_filters(self) -> RetrieveFilters:
        invalid_statuses = sorted({value for value in self.statuses if value not in VALID_STATUS})
        if invalid_statuses:
            raise ValueError(f"unsupported statuses {invalid_statuses}")
        invalid_types = sorted(
            {value for value in self.object_types if value not in CORE_OBJECT_TYPES}
        )
        if invalid_types:
            raise ValueError(f"unsupported object types {invalid_types}")
        return self


class RetrieveRequest(ContractModel):
    query: str | dict[str, Any]
    query_modes: list[RetrieveQueryMode] = Field(min_length=1)
    budget: BudgetConstraint
    filters: RetrieveFilters = Field(default_factory=RetrieveFilters)


class RetrieveResponse(ContractModel):
    candidate_ids: list[str] = Field(default_factory=list)
    scores: list[float] = Field(default_factory=list)
    candidate_summaries: list[dict[str, Any]] = Field(default_factory=list)
    evidence_summary: str | dict[str, Any]

    @model_validator(mode="after")
    def match_scores_to_candidates(self) -> RetrieveResponse:
        if len(self.candidate_ids) != len(self.scores):
            raise ValueError("candidate_ids and scores must have the same length")
        if self.candidate_summaries and len(self.candidate_summaries) != len(self.candidate_ids):
            raise ValueError("candidate_summaries and candidate_ids must have the same length")
        return self


class SummarizeRequest(ContractModel):
    input_refs: list[str] = Field(min_length=1)
    summary_scope: str = Field(min_length=1)
    target_kind: str = Field(min_length=1)


class SummarizeResponse(ContractModel):
    summary_object_id: str = Field(min_length=1)


class LinkRequest(ContractModel):
    src_id: str = Field(min_length=1)
    dst_id: str = Field(min_length=1)
    relation_type: str = Field(min_length=1)
    evidence_refs: list[str] = Field(min_length=1)


class LinkResponse(ContractModel):
    link_object_id: str = Field(min_length=1)


class ReflectRequest(ContractModel):
    episode_id: str = Field(min_length=1)
    focus: str | dict[str, Any]


class ReflectResponse(ContractModel):
    reflection_object_id: str = Field(min_length=1)


class ReorganizeSimpleRequest(ContractModel):
    target_refs: list[str] = Field(min_length=1)
    operation: ReorganizeOperation
    reason: str = Field(min_length=1)


class ReorganizeSimpleResponse(ContractModel):
    updated_ids: list[str] = Field(default_factory=list)
    new_object_ids: list[str] = Field(default_factory=list)


class PrimitiveExecutionResult(ContractModel):
    primitive: PrimitiveName
    outcome: PrimitiveOutcome
    response: dict[str, Any] | None = None
    error: PrimitiveError | None = None
    target_ids: list[str] = Field(default_factory=list)
    cost: list[BudgetCost] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_outcome_shape(self) -> PrimitiveExecutionResult:
        if self.outcome is PrimitiveOutcome.SUCCESS:
            if self.response is None or self.error is not None:
                raise ValueError("successful result requires response and forbids error")
        else:
            if self.response is not None or self.error is None:
                raise ValueError("non-success result requires error and forbids response")
        return self


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
