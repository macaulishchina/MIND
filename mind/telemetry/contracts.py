"""Typed contracts for Phase L development telemetry."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TelemetryModel(BaseModel):
    """Strict base model shared by telemetry contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class TelemetryScope(StrEnum):
    PRIMITIVE = "primitive"
    RETRIEVAL = "retrieval"
    WORKSPACE = "workspace"
    ACCESS = "access"
    OFFLINE = "offline"
    GOVERNANCE = "governance"
    OBJECT_DELTA = "object_delta"


TELEMETRY_COVERAGE_SURFACES: tuple[TelemetryScope, ...] = (
    TelemetryScope.PRIMITIVE,
    TelemetryScope.RETRIEVAL,
    TelemetryScope.WORKSPACE,
    TelemetryScope.ACCESS,
    TelemetryScope.OFFLINE,
    TelemetryScope.GOVERNANCE,
    TelemetryScope.OBJECT_DELTA,
)


class TelemetryEventKind(StrEnum):
    ENTRY = "entry"
    DECISION = "decision"
    STATE_DELTA = "state_delta"
    CONTEXT_RESULT = "context_result"
    ACTION_RESULT = "action_result"


class TelemetryEvent(TelemetryModel):
    event_id: str = Field(min_length=1)
    scope: TelemetryScope
    kind: TelemetryEventKind
    occurred_at: datetime
    run_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    parent_event_id: str | None = None
    job_id: str | None = None
    workspace_id: str | None = None
    object_id: str | None = None
    object_version: int | None = Field(default=None, ge=1)
    actor: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    delta: dict[str, Any] | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    debug_fields: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def enforce_shape(self) -> TelemetryEvent:
        delta_fields = (self.before, self.after, self.delta)
        has_any_delta = any(field is not None for field in delta_fields)
        has_all_delta = all(field is not None for field in delta_fields)
        if has_any_delta and not has_all_delta:
            raise ValueError("before/after/delta must be provided together")
        if self.kind is TelemetryEventKind.STATE_DELTA:
            if not has_all_delta:
                raise ValueError("state_delta events require before/after/delta")
            if not self.object_id:
                raise ValueError("state_delta events require object_id")
        if self.scope is TelemetryScope.WORKSPACE and not self.workspace_id:
            raise ValueError("workspace events require workspace_id")
        if self.scope in {TelemetryScope.OFFLINE, TelemetryScope.GOVERNANCE} and not self.job_id:
            raise ValueError("offline/governance events require job_id")
        if self.scope is TelemetryScope.OBJECT_DELTA and not self.object_id:
            raise ValueError("object_delta events require object_id")
        return self
