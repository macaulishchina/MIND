"""Typed contracts for runtime access modes and trace output."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mind.primitives.contracts import RetrieveFilters, RetrieveQueryMode


class AccessModel(BaseModel):
    """Strict base model shared by access-mode contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class AccessMode(StrEnum):
    FLASH = "flash"
    RECALL = "recall"
    RECONSTRUCT = "reconstruct"
    REFLECTIVE_ACCESS = "reflective_access"
    AUTO = "auto"


class AccessTaskFamily(StrEnum):
    SPEED_SENSITIVE = "speed_sensitive"
    BALANCED = "balanced"
    HIGH_CORRECTNESS = "high_correctness"


class AccessContextKind(StrEnum):
    RAW_TOPK = "raw_topk"
    WORKSPACE = "workspace"


class AccessTraceKind(StrEnum):
    SELECT_MODE = "select_mode"
    RETRIEVE = "retrieve"
    READ = "read"
    WORKSPACE = "workspace"
    VERIFY = "verify"
    MODE_SUMMARY = "mode_summary"


class AccessSwitchKind(StrEnum):
    INITIAL = "initial"
    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    JUMP = "jump"


class AccessReasonCode(StrEnum):
    EXPLICIT_MODE_REQUEST = "explicit_mode_request"
    LATENCY_SENSITIVE = "latency_sensitive"
    BALANCED_DEFAULT = "balanced_default"
    CROSS_EPISODE_REQUIRED = "cross_episode_required"
    HIGH_CORRECTNESS_REQUIRED = "high_correctness_required"
    COVERAGE_INSUFFICIENT = "coverage_insufficient"
    EVIDENCE_CONFLICT = "evidence_conflict"
    CONSTRAINT_RISK = "constraint_risk"
    BUDGET_PRESSURE = "budget_pressure"
    QUALITY_SATISFIED = "quality_satisfied"


class AccessModeRequest(AccessModel):
    """Frozen request contract for fixed access modes and `auto`."""

    requested_mode: AccessMode = AccessMode.AUTO
    task_family: AccessTaskFamily | None = None
    time_budget_ms: int | None = Field(default=None, ge=1)
    hard_constraints: list[str] = Field(default_factory=list)


class AccessRunRequest(AccessModeRequest):
    """Request contract for fixed or auto runtime access execution."""

    query: str | dict[str, Any]
    task_id: str = Field(min_length=1)
    query_modes: list[RetrieveQueryMode] = Field(
        default_factory=lambda: [RetrieveQueryMode.KEYWORD],
        min_length=1,
    )
    filters: RetrieveFilters = Field(default_factory=RetrieveFilters)


class AccessModeTraceEvent(AccessModel):
    """A single runtime access trace event."""

    event_kind: AccessTraceKind
    mode: AccessMode
    summary: str = Field(min_length=1)
    reason_code: AccessReasonCode | None = None
    switch_kind: AccessSwitchKind | None = None
    from_mode: AccessMode | None = None
    target_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_effective_mode(self) -> AccessModeTraceEvent:
        if self.mode is AccessMode.AUTO:
            raise ValueError("trace events must record an effective fixed access mode")
        return self

    @model_validator(mode="after")
    def enforce_switch_contract(self) -> AccessModeTraceEvent:
        if self.event_kind is AccessTraceKind.SELECT_MODE:
            if self.switch_kind is None or self.reason_code is None:
                raise ValueError("select_mode events require switch_kind and reason_code")
            if self.switch_kind is AccessSwitchKind.INITIAL:
                if self.from_mode is not None:
                    raise ValueError("initial select_mode events must not define from_mode")
                return self
            if self.from_mode is None:
                raise ValueError("non-initial select_mode events require from_mode")
            if self.from_mode is AccessMode.AUTO:
                raise ValueError("from_mode must be a fixed access mode")
            if self.from_mode is self.mode:
                raise ValueError("mode switches must change the effective mode")
            return self

        if self.switch_kind is not None or self.from_mode is not None:
            raise ValueError("only select_mode events may define switch metadata")
        return self


class AccessRunTrace(AccessModel):
    """Frozen runtime trace contract for a single access-mode execution."""

    requested_mode: AccessMode
    resolved_mode: AccessMode
    task_family: AccessTaskFamily | None = None
    time_budget_ms: int | None = Field(default=None, ge=1)
    hard_constraints: list[str] = Field(default_factory=list)
    events: list[AccessModeTraceEvent] = Field(min_length=2)

    @model_validator(mode="after")
    def enforce_resolved_mode(self) -> AccessRunTrace:
        if self.resolved_mode is AccessMode.AUTO:
            raise ValueError("resolved_mode must be a fixed access mode")
        if (
            self.requested_mode is not AccessMode.AUTO
            and self.resolved_mode is not self.requested_mode
        ):
            raise ValueError("explicit fixed mode requests must not be overridden")
        return self

    @model_validator(mode="after")
    def enforce_trace_shape(self) -> AccessRunTrace:
        if self.events[0].event_kind is not AccessTraceKind.SELECT_MODE:
            raise ValueError("access trace must start with select_mode")
        if self.events[-1].event_kind is not AccessTraceKind.MODE_SUMMARY:
            raise ValueError("access trace must end with mode_summary")
        if self.events[-1].mode is not self.resolved_mode:
            raise ValueError("final mode_summary must match resolved_mode")
        return self

    @model_validator(mode="after")
    def enforce_explicit_mode_lock(self) -> AccessRunTrace:
        if self.requested_mode is AccessMode.AUTO:
            if self.events[0].switch_kind is not AccessSwitchKind.INITIAL:
                raise ValueError("auto runs must begin with an initial mode selection")
            return self

        if self.events[0].reason_code is not AccessReasonCode.EXPLICIT_MODE_REQUEST:
            raise ValueError("fixed mode runs must record explicit_mode_request")
        if self.events[0].switch_kind is not AccessSwitchKind.INITIAL:
            raise ValueError("fixed mode runs must begin with an initial mode selection")
        if self.events[0].mode is not self.requested_mode:
            raise ValueError("fixed mode runs must select the requested mode first")
        extra_select_events = [
            event for event in self.events[1:] if event.event_kind is AccessTraceKind.SELECT_MODE
        ]
        if extra_select_events:
            raise ValueError("fixed mode runs must not contain auto-driven mode switches")
        return self


class AccessRunResponse(AccessModel):
    """Frozen response contract for a completed fixed access execution."""

    resolved_mode: AccessMode
    context_kind: AccessContextKind
    context_object_ids: list[str] = Field(default_factory=list)
    context_text: str = Field(min_length=1)
    context_token_count: int = Field(ge=0)
    candidate_ids: list[str] = Field(default_factory=list)
    candidate_summaries: list[dict[str, Any]] = Field(default_factory=list)
    read_object_ids: list[str] = Field(default_factory=list)
    expanded_object_ids: list[str] = Field(default_factory=list)
    selected_object_ids: list[str] = Field(default_factory=list)
    selected_summaries: list[dict[str, Any]] = Field(default_factory=list)
    answer_text: str | None = None
    answer_support_ids: list[str] = Field(default_factory=list)
    answer_trace: dict[str, Any] | None = None
    verification_notes: list[str] = Field(default_factory=list)
    trace: AccessRunTrace

    @model_validator(mode="after")
    def enforce_response_shape(self) -> AccessRunResponse:
        if self.resolved_mode is AccessMode.AUTO:
            raise ValueError("resolved_mode must be a fixed access mode")
        if self.context_kind is AccessContextKind.RAW_TOPK:
            if self.resolved_mode is not AccessMode.FLASH:
                raise ValueError("raw_topk context is only valid for flash mode")
            if self.selected_object_ids:
                raise ValueError("raw_topk responses must not define selected_object_ids")
        else:
            if self.resolved_mode is AccessMode.FLASH:
                raise ValueError("flash mode must not return a workspace context")
            if not self.selected_object_ids:
                raise ValueError("workspace responses require selected_object_ids")

        if self.resolved_mode is AccessMode.REFLECTIVE_ACCESS:
            if not self.verification_notes:
                raise ValueError("reflective access responses require verification notes")
        elif self.verification_notes:
            raise ValueError("only reflective access may define verification notes")
        if self.candidate_summaries and len(self.candidate_summaries) > len(self.candidate_ids):
            raise ValueError("candidate_summaries cannot exceed candidate_ids")
        if self.selected_summaries and len(self.selected_summaries) != len(self.selected_object_ids):
            raise ValueError("selected_summaries must match selected_object_ids")
        if self.answer_trace is not None and not self.answer_text:
            raise ValueError("answer_trace requires answer_text")
        if self.answer_support_ids and not self.answer_text:
            raise ValueError("answer_support_ids require answer_text")

        return self
