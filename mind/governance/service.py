"""Minimal governance control-plane service for conceal workflows."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from uuid import uuid4

from mind.kernel.governance import (
    ConcealExecuteRequest,
    ConcealExecuteResult,
    ConcealmentRecord,
    ConcealPlanRequest,
    ConcealPlanResult,
    ConcealPreviewRequest,
    ConcealPreviewResult,
    ConcealSelector,
    GovernanceAction,
    GovernanceAuditRecord,
    GovernanceCapability,
    GovernanceOutcome,
    GovernanceStage,
)
from mind.kernel.provenance import DirectProvenanceRecord, build_provenance_summary
from mind.kernel.store import MemoryStore
from mind.primitives.contracts import Capability, PrimitiveExecutionContext


class GovernanceServiceError(RuntimeError):
    """Raised when a governance workflow cannot be executed safely."""


class GovernanceService:
    """Library-first governance surface for minimal conceal workflows."""

    def __init__(
        self,
        store: MemoryStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self._clock = clock or _utc_now

    def plan_conceal(
        self,
        request: ConcealPlanRequest | dict[str, object],
        context: PrimitiveExecutionContext | dict[str, object],
    ) -> ConcealPlanResult:
        validated_request = ConcealPlanRequest.model_validate(request)
        execution_context = PrimitiveExecutionContext.model_validate(context)
        self._require_capability(
            execution_context,
            Capability.GOVERNANCE_PLAN,
            action="plan conceal governance operations",
        )

        operation_id = self._new_id("conceal-op")
        records = self._resolve_selector(
            validated_request.selector,
            self.store.iter_direct_provenance(),
        )
        candidate_object_ids = [record.bound_object_id for record in records]
        candidate_provenance_ids = [record.provenance_id for record in records]
        already_concealed_object_ids = [
            object_id
            for object_id in candidate_object_ids
            if self.store.is_object_concealed(object_id)
        ]
        self.store.record_governance_audit(
            GovernanceAuditRecord(
                audit_id=self._new_audit_id(GovernanceStage.PLAN),
                operation_id=operation_id,
                action=GovernanceAction.CONCEAL,
                stage=GovernanceStage.PLAN,
                actor=execution_context.actor,
                capability=GovernanceCapability.GOVERNANCE_PLAN,
                timestamp=self._clock(),
                outcome=GovernanceOutcome.SUCCEEDED,
                reason=validated_request.reason,
                target_object_ids=candidate_object_ids,
                target_provenance_ids=candidate_provenance_ids,
                selection=validated_request.selector.model_dump(mode="json"),
                summary={
                    "candidate_object_count": len(candidate_object_ids),
                    "already_concealed_count": len(already_concealed_object_ids),
                },
            )
        )
        return ConcealPlanResult(
            operation_id=operation_id,
            candidate_object_ids=candidate_object_ids,
            candidate_provenance_ids=candidate_provenance_ids,
            already_concealed_object_ids=already_concealed_object_ids,
            selection=validated_request.selector.model_dump(mode="json"),
        )

    def preview_conceal(
        self,
        request: ConcealPreviewRequest | dict[str, object],
        context: PrimitiveExecutionContext | dict[str, object],
    ) -> ConcealPreviewResult:
        validated_request = ConcealPreviewRequest.model_validate(request)
        execution_context = PrimitiveExecutionContext.model_validate(context)
        self._require_capability(
            execution_context,
            Capability.GOVERNANCE_PLAN,
            action="preview conceal governance operations",
        )

        plan_audit = self._require_stage_audit(
            validated_request.operation_id,
            GovernanceStage.PLAN,
        )
        selector = ConcealSelector.model_validate(plan_audit.selection)
        records = self._resolve_selector(selector, self.store.iter_direct_provenance())
        candidate_object_ids = [record.bound_object_id for record in records]
        candidate_provenance_ids = [record.provenance_id for record in records]
        already_concealed_object_ids = [
            object_id
            for object_id in candidate_object_ids
            if self.store.is_object_concealed(object_id)
        ]
        provenance_summaries = {
            record.bound_object_id: build_provenance_summary(record)
            for record in records
        }
        self.store.record_governance_audit(
            GovernanceAuditRecord(
                audit_id=self._new_audit_id(GovernanceStage.PREVIEW),
                operation_id=validated_request.operation_id,
                action=GovernanceAction.CONCEAL,
                stage=GovernanceStage.PREVIEW,
                actor=execution_context.actor,
                capability=GovernanceCapability.GOVERNANCE_PLAN,
                timestamp=self._clock(),
                outcome=GovernanceOutcome.SUCCEEDED,
                reason=plan_audit.reason,
                target_object_ids=candidate_object_ids,
                target_provenance_ids=candidate_provenance_ids,
                selection=selector.model_dump(mode="json"),
                summary={
                    "candidate_object_count": len(candidate_object_ids),
                    "already_concealed_count": len(already_concealed_object_ids),
                },
            )
        )
        return ConcealPreviewResult(
            operation_id=validated_request.operation_id,
            candidate_object_ids=candidate_object_ids,
            already_concealed_object_ids=already_concealed_object_ids,
            provenance_summaries=provenance_summaries,
        )

    def execute_conceal(
        self,
        request: ConcealExecuteRequest | dict[str, object],
        context: PrimitiveExecutionContext | dict[str, object],
    ) -> ConcealExecuteResult:
        validated_request = ConcealExecuteRequest.model_validate(request)
        execution_context = PrimitiveExecutionContext.model_validate(context)
        self._require_capability(
            execution_context,
            Capability.GOVERNANCE_EXECUTE,
            action="execute conceal governance operations",
        )

        plan_audit = self._require_stage_audit(
            validated_request.operation_id,
            GovernanceStage.PLAN,
        )
        self._require_stage_audit(validated_request.operation_id, GovernanceStage.PREVIEW)
        selector = ConcealSelector.model_validate(plan_audit.selection)

        with self.store.transaction() as transaction:
            records = self._resolve_selector(selector, transaction.iter_direct_provenance())
            candidate_object_ids = [record.bound_object_id for record in records]
            candidate_provenance_ids = [record.provenance_id for record in records]
            concealed_object_ids: list[str] = []
            already_concealed_object_ids: list[str] = []

            for index, record in enumerate(records, start=1):
                if transaction.is_object_concealed(record.bound_object_id):
                    already_concealed_object_ids.append(record.bound_object_id)
                    continue
                transaction.record_concealment(
                    ConcealmentRecord(
                        concealment_id=self._new_id(
                            f"conceal-{validated_request.operation_id}-{index}"
                        ),
                        operation_id=validated_request.operation_id,
                        object_id=record.bound_object_id,
                        actor=execution_context.actor,
                        concealed_at=self._clock(),
                        reason=plan_audit.reason,
                    )
                )
                concealed_object_ids.append(record.bound_object_id)

            transaction.record_governance_audit(
                GovernanceAuditRecord(
                    audit_id=self._new_audit_id(GovernanceStage.EXECUTE),
                    operation_id=validated_request.operation_id,
                    action=GovernanceAction.CONCEAL,
                    stage=GovernanceStage.EXECUTE,
                    actor=execution_context.actor,
                    capability=GovernanceCapability.GOVERNANCE_EXECUTE,
                    timestamp=self._clock(),
                    outcome=GovernanceOutcome.SUCCEEDED,
                    reason=plan_audit.reason,
                    target_object_ids=candidate_object_ids,
                    target_provenance_ids=candidate_provenance_ids,
                    selection=selector.model_dump(mode="json"),
                    summary={
                        "candidate_object_count": len(candidate_object_ids),
                        "concealed_object_count": len(concealed_object_ids),
                        "already_concealed_count": len(already_concealed_object_ids),
                    },
                )
            )

        return ConcealExecuteResult(
            operation_id=validated_request.operation_id,
            concealed_object_ids=concealed_object_ids,
            already_concealed_object_ids=already_concealed_object_ids,
        )

    def _require_stage_audit(
        self,
        operation_id: str,
        stage: GovernanceStage,
    ) -> GovernanceAuditRecord:
        rows = self.store.iter_governance_audit_for_operation(operation_id)
        matches = [
            row
            for row in rows
            if row.stage == stage and row.action == GovernanceAction.CONCEAL
        ]
        if not matches:
            raise GovernanceServiceError(
                f"conceal operation '{operation_id}' missing governance {stage.value} audit"
            )
        return matches[-1]

    @staticmethod
    def _resolve_selector(
        selector: ConcealSelector,
        records: Iterable[DirectProvenanceRecord],
    ) -> list[DirectProvenanceRecord]:
        object_ids = set(selector.object_ids)
        provenance_ids = set(selector.provenance_ids)
        matched: list[DirectProvenanceRecord] = []
        for record in records:
            if object_ids and record.bound_object_id not in object_ids:
                continue
            if provenance_ids and record.provenance_id not in provenance_ids:
                continue
            if (
                selector.producer_kind is not None
                and record.producer_kind != selector.producer_kind
            ):
                continue
            if selector.producer_id is not None and record.producer_id != selector.producer_id:
                continue
            if selector.user_id is not None and record.user_id != selector.user_id:
                continue
            if selector.model_id is not None and record.model_id != selector.model_id:
                continue
            if selector.episode_id is not None and record.episode_id != selector.episode_id:
                continue
            if selector.captured_after is not None and record.captured_at < selector.captured_after:
                continue
            if (
                selector.captured_before is not None
                and record.captured_at > selector.captured_before
            ):
                continue
            matched.append(record)

        matched.sort(key=lambda item: (item.captured_at, item.provenance_id))
        return matched

    @staticmethod
    def _require_capability(
        context: PrimitiveExecutionContext,
        capability: Capability,
        *,
        action: str,
    ) -> None:
        if capability in context.capabilities:
            return
        raise GovernanceServiceError(
            f"capability '{capability.value}' required to {action}"
        )

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}-{uuid4().hex[:12]}"

    @classmethod
    def _new_audit_id(cls, stage: GovernanceStage) -> str:
        stage_prefix = {
            GovernanceStage.PLAN: "01-plan",
            GovernanceStage.PREVIEW: "02-preview",
            GovernanceStage.EXECUTE: "03-execute",
            GovernanceStage.APPROVE: "04-approve",
        }[stage]
        return cls._new_id(f"gov-audit-{stage_prefix}")


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)
