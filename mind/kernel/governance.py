"""Governance audit models for the control plane."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .provenance import ProducerKind, ProvenanceSummary


class GovernanceModel(BaseModel):
    """Strict base model shared by governance control-plane records."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class GovernanceAction(StrEnum):
    CONCEAL = "conceal"
    ERASE = "erase"
    RESHAPE = "reshape"


class GovernanceStage(StrEnum):
    PLAN = "plan"
    PREVIEW = "preview"
    APPROVE = "approve"
    EXECUTE = "execute"


class GovernanceCapability(StrEnum):
    GOVERNANCE_PLAN = "governance_plan"
    GOVERNANCE_EXECUTE = "governance_execute"
    GOVERNANCE_APPROVE_FULL_ERASE = "governance_approve_full_erase"


class GovernanceScope(StrEnum):
    MEMORY_WORLD = "memory_world"
    MEMORY_WORLD_PLUS_ARTIFACTS = "memory_world_plus_artifacts"
    FULL = "full"


class GovernanceOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    FAILED = "failed"


class ConcealmentRecord(GovernanceModel):
    concealment_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    object_id: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    concealed_at: datetime
    reason: str | None = Field(default=None, min_length=1)


class ConcealSelector(GovernanceModel):
    object_ids: list[str] = Field(default_factory=list)
    provenance_ids: list[str] = Field(default_factory=list)
    producer_kind: ProducerKind | None = None
    producer_id: str | None = Field(default=None, min_length=1)
    user_id: str | None = Field(default=None, min_length=1)
    model_id: str | None = Field(default=None, min_length=1)
    episode_id: str | None = Field(default=None, min_length=1)
    captured_after: datetime | None = None
    captured_before: datetime | None = None

    @model_validator(mode="after")
    def require_at_least_one_filter(self) -> ConcealSelector:
        if not (
            self.object_ids
            or self.provenance_ids
            or self.producer_kind is not None
            or self.producer_id is not None
            or self.user_id is not None
            or self.model_id is not None
            or self.episode_id is not None
            or self.captured_after is not None
            or self.captured_before is not None
        ):
            raise ValueError("conceal selector must define at least one filter")
        return self

    @model_validator(mode="after")
    def enforce_time_window(self) -> ConcealSelector:
        if (
            self.captured_after is not None
            and self.captured_before is not None
            and self.captured_after > self.captured_before
        ):
            raise ValueError("captured_after must be <= captured_before")
        return self


class ConcealPlanRequest(GovernanceModel):
    selector: ConcealSelector
    reason: str = Field(min_length=1)


class ConcealPlanResult(GovernanceModel):
    operation_id: str = Field(min_length=1)
    candidate_object_ids: list[str] = Field(default_factory=list)
    candidate_provenance_ids: list[str] = Field(default_factory=list)
    already_concealed_object_ids: list[str] = Field(default_factory=list)
    selection: dict[str, Any] = Field(default_factory=dict)


class ConcealPreviewRequest(GovernanceModel):
    operation_id: str = Field(min_length=1)


class ConcealPreviewResult(GovernanceModel):
    operation_id: str = Field(min_length=1)
    candidate_object_ids: list[str] = Field(default_factory=list)
    already_concealed_object_ids: list[str] = Field(default_factory=list)
    provenance_summaries: dict[str, ProvenanceSummary] = Field(default_factory=dict)


class ConcealExecuteRequest(GovernanceModel):
    operation_id: str = Field(min_length=1)


class ConcealExecuteResult(GovernanceModel):
    operation_id: str = Field(min_length=1)
    concealed_object_ids: list[str] = Field(default_factory=list)
    already_concealed_object_ids: list[str] = Field(default_factory=list)


class GovernanceAuditRecord(GovernanceModel):
    audit_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    action: GovernanceAction
    stage: GovernanceStage
    actor: str = Field(min_length=1)
    capability: GovernanceCapability
    timestamp: datetime
    outcome: GovernanceOutcome
    scope: GovernanceScope | None = None
    reason: str | None = Field(default=None, min_length=1)
    target_object_ids: list[str] = Field(default_factory=list)
    target_provenance_ids: list[str] = Field(default_factory=list)
    selection: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def enforce_stage_capability_contract(self) -> GovernanceAuditRecord:
        if self.stage in {GovernanceStage.PLAN, GovernanceStage.PREVIEW}:
            expected = GovernanceCapability.GOVERNANCE_PLAN
        elif self.stage is GovernanceStage.EXECUTE:
            expected = GovernanceCapability.GOVERNANCE_EXECUTE
        else:
            expected = GovernanceCapability.GOVERNANCE_APPROVE_FULL_ERASE

        if self.capability is not expected:
            raise ValueError(
                f"governance stage '{self.stage.value}' requires capability "
                f"'{expected.value}'"
            )
        return self

    @model_validator(mode="after")
    def enforce_scope_contract(self) -> GovernanceAuditRecord:
        if self.action is GovernanceAction.ERASE and self.scope is None:
            raise ValueError("governance action 'erase' requires an explicit scope")
        if self.stage is GovernanceStage.APPROVE:
            if self.action is not GovernanceAction.ERASE:
                raise ValueError("governance stage 'approve' is only valid for 'erase'")
            if self.scope is not GovernanceScope.FULL:
                raise ValueError("governance stage 'approve' requires scope 'full'")
        return self
