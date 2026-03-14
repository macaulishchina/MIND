"""Minimal governance control-plane service for conceal workflows."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

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
from mind.kernel.provenance import build_provenance_summary
from mind.kernel.store import MemoryStore
from mind.primitives.contracts import Capability, PrimitiveExecutionContext
from mind.telemetry import TelemetryEvent, TelemetryEventKind, TelemetryRecorder, TelemetryScope

from .service_helpers import (
    GovernanceServiceError,  # noqa: F401
    new_audit_id,
    new_governance_id,
    record_telemetry,
    require_capability,
    require_stage_audit,
    resolve_selector,
    utc_now,
)


class GovernanceService:
    """Library-first governance surface for minimal conceal workflows."""

    def __init__(
        self,
        store: MemoryStore,
        *,
        clock: Callable[[], datetime] | None = None,
        telemetry_recorder: TelemetryRecorder | None = None,
    ) -> None:
        self.store = store
        self._clock = clock or utc_now
        self._telemetry_recorder = telemetry_recorder

    def plan_conceal(
        self,
        request: ConcealPlanRequest | dict[str, object],
        context: PrimitiveExecutionContext | dict[str, object],
    ) -> ConcealPlanResult:
        validated_request = ConcealPlanRequest.model_validate(request)
        execution_context = PrimitiveExecutionContext.model_validate(context)
        operation_id = new_governance_id("conceal-op")
        run_id = execution_context.telemetry_run_id or f"governance-{operation_id}"
        event_prefix = f"governance-plan-{operation_id}"
        last_parent_event_id = f"{event_prefix}-entry"
        record_telemetry(self._telemetry_recorder, enabled=execution_context.dev_mode,
            event=TelemetryEvent(
                event_id=last_parent_event_id,
                scope=TelemetryScope.GOVERNANCE,
                kind=TelemetryEventKind.ENTRY,
                occurred_at=self._clock(),
                run_id=run_id,
                operation_id=operation_id,
                job_id=operation_id,
                actor=execution_context.actor,
                payload={
                    "stage": "plan",
                    "action": GovernanceAction.CONCEAL.value,
                    "selection": validated_request.selector.model_dump(mode="json"),
                    "reason": validated_request.reason,
                },
            ),
        )

        try:
            require_capability(
                execution_context,
                Capability.GOVERNANCE_PLAN,
                action="plan conceal governance operations",
            )
            records = resolve_selector(
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
            last_parent_event_id = f"{event_prefix}-selection"
            record_telemetry(self._telemetry_recorder, enabled=execution_context.dev_mode,
                event=TelemetryEvent(
                    event_id=last_parent_event_id,
                    scope=TelemetryScope.GOVERNANCE,
                    kind=TelemetryEventKind.DECISION,
                    occurred_at=self._clock(),
                    run_id=run_id,
                    operation_id=operation_id,
                    parent_event_id=f"{event_prefix}-entry",
                    job_id=operation_id,
                    actor=execution_context.actor,
                    payload={
                        "stage": "plan_selection",
                        "candidate_object_ids": candidate_object_ids,
                        "candidate_provenance_ids": candidate_provenance_ids,
                        "already_concealed_object_ids": already_concealed_object_ids,
                    },
                    debug_fields={
                        "candidate_object_count": len(candidate_object_ids),
                        "already_concealed_count": len(already_concealed_object_ids),
                    },
                ),
            )
            self.store.record_governance_audit(
                GovernanceAuditRecord(
                    audit_id=new_audit_id(GovernanceStage.PLAN),
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
        except Exception as exc:
            record_telemetry(self._telemetry_recorder, enabled=execution_context.dev_mode,
                event=TelemetryEvent(
                    event_id=f"{event_prefix}-result",
                    scope=TelemetryScope.GOVERNANCE,
                    kind=TelemetryEventKind.ACTION_RESULT,
                    occurred_at=self._clock(),
                    run_id=run_id,
                    operation_id=operation_id,
                    parent_event_id=last_parent_event_id,
                    job_id=operation_id,
                    actor=execution_context.actor,
                    payload={
                        "stage": "plan",
                        "outcome": "failure",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    },
                ),
            )
            raise

        result = ConcealPlanResult(
            operation_id=operation_id,
            candidate_object_ids=candidate_object_ids,
            candidate_provenance_ids=candidate_provenance_ids,
            already_concealed_object_ids=already_concealed_object_ids,
            selection=validated_request.selector.model_dump(mode="json"),
        )
        record_telemetry(self._telemetry_recorder, enabled=execution_context.dev_mode,
            event=TelemetryEvent(
                event_id=f"{event_prefix}-result",
                scope=TelemetryScope.GOVERNANCE,
                kind=TelemetryEventKind.ACTION_RESULT,
                occurred_at=self._clock(),
                run_id=run_id,
                operation_id=operation_id,
                parent_event_id=last_parent_event_id,
                job_id=operation_id,
                actor=execution_context.actor,
                payload={
                    "stage": "plan",
                    "outcome": "success",
                    "result": result.model_dump(mode="json"),
                },
            ),
        )
        return result

    def preview_conceal(
        self,
        request: ConcealPreviewRequest | dict[str, object],
        context: PrimitiveExecutionContext | dict[str, object],
    ) -> ConcealPreviewResult:
        validated_request = ConcealPreviewRequest.model_validate(request)
        execution_context = PrimitiveExecutionContext.model_validate(context)
        operation_id = validated_request.operation_id
        run_id = execution_context.telemetry_run_id or f"governance-{operation_id}"
        event_prefix = f"governance-preview-{operation_id}"
        last_parent_event_id = f"{event_prefix}-entry"
        record_telemetry(self._telemetry_recorder, enabled=execution_context.dev_mode,
            event=TelemetryEvent(
                event_id=last_parent_event_id,
                scope=TelemetryScope.GOVERNANCE,
                kind=TelemetryEventKind.ENTRY,
                occurred_at=self._clock(),
                run_id=run_id,
                operation_id=operation_id,
                job_id=operation_id,
                actor=execution_context.actor,
                payload={
                    "stage": "preview",
                    "action": GovernanceAction.CONCEAL.value,
                },
            ),
        )

        try:
            require_capability(
                execution_context,
                Capability.GOVERNANCE_PLAN,
                action="preview conceal governance operations",
            )

            plan_audit = require_stage_audit(self.store, 
                validated_request.operation_id,
                GovernanceStage.PLAN,
            )
            selector = ConcealSelector.model_validate(plan_audit.selection)
            records = resolve_selector(selector, self.store.iter_direct_provenance())
            candidate_object_ids = [record.bound_object_id for record in records]
            candidate_provenance_ids = [record.provenance_id for record in records]
            already_concealed_object_ids = [
                object_id
                for object_id in candidate_object_ids
                if self.store.is_object_concealed(object_id)
            ]
            provenance_summaries = {
                record.bound_object_id: build_provenance_summary(record) for record in records
            }
            last_parent_event_id = f"{event_prefix}-selection"
            record_telemetry(self._telemetry_recorder, enabled=execution_context.dev_mode,
                event=TelemetryEvent(
                    event_id=last_parent_event_id,
                    scope=TelemetryScope.GOVERNANCE,
                    kind=TelemetryEventKind.DECISION,
                    occurred_at=self._clock(),
                    run_id=run_id,
                    operation_id=operation_id,
                    parent_event_id=f"{event_prefix}-entry",
                    job_id=operation_id,
                    actor=execution_context.actor,
                    payload={
                        "stage": "preview_selection",
                        "candidate_object_ids": candidate_object_ids,
                        "already_concealed_object_ids": already_concealed_object_ids,
                    },
                    debug_fields={
                        "candidate_object_count": len(candidate_object_ids),
                        "provenance_summary_count": len(provenance_summaries),
                    },
                ),
            )
            self.store.record_governance_audit(
                GovernanceAuditRecord(
                    audit_id=new_audit_id(GovernanceStage.PREVIEW),
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
        except Exception as exc:
            record_telemetry(self._telemetry_recorder, enabled=execution_context.dev_mode,
                event=TelemetryEvent(
                    event_id=f"{event_prefix}-result",
                    scope=TelemetryScope.GOVERNANCE,
                    kind=TelemetryEventKind.ACTION_RESULT,
                    occurred_at=self._clock(),
                    run_id=run_id,
                    operation_id=operation_id,
                    parent_event_id=last_parent_event_id,
                    job_id=operation_id,
                    actor=execution_context.actor,
                    payload={
                        "stage": "preview",
                        "outcome": "failure",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    },
                ),
            )
            raise

        result = ConcealPreviewResult(
            operation_id=validated_request.operation_id,
            candidate_object_ids=candidate_object_ids,
            already_concealed_object_ids=already_concealed_object_ids,
            provenance_summaries=provenance_summaries,
        )
        record_telemetry(self._telemetry_recorder, enabled=execution_context.dev_mode,
            event=TelemetryEvent(
                event_id=f"{event_prefix}-result",
                scope=TelemetryScope.GOVERNANCE,
                kind=TelemetryEventKind.ACTION_RESULT,
                occurred_at=self._clock(),
                run_id=run_id,
                operation_id=operation_id,
                parent_event_id=last_parent_event_id,
                job_id=operation_id,
                actor=execution_context.actor,
                payload={
                    "stage": "preview",
                    "outcome": "success",
                    "result": result.model_dump(mode="json"),
                },
            ),
        )
        return result

    def execute_conceal(
        self,
        request: ConcealExecuteRequest | dict[str, object],
        context: PrimitiveExecutionContext | dict[str, object],
    ) -> ConcealExecuteResult:
        validated_request = ConcealExecuteRequest.model_validate(request)
        execution_context = PrimitiveExecutionContext.model_validate(context)
        operation_id = validated_request.operation_id
        run_id = execution_context.telemetry_run_id or f"governance-{operation_id}"
        event_prefix = f"governance-execute-{operation_id}"
        last_parent_event_id = f"{event_prefix}-entry"
        record_telemetry(self._telemetry_recorder, enabled=execution_context.dev_mode,
            event=TelemetryEvent(
                event_id=last_parent_event_id,
                scope=TelemetryScope.GOVERNANCE,
                kind=TelemetryEventKind.ENTRY,
                occurred_at=self._clock(),
                run_id=run_id,
                operation_id=operation_id,
                job_id=operation_id,
                actor=execution_context.actor,
                payload={
                    "stage": "execute",
                    "action": GovernanceAction.CONCEAL.value,
                },
            ),
        )

        try:
            require_capability(
                execution_context,
                Capability.GOVERNANCE_EXECUTE,
                action="execute conceal governance operations",
            )

            plan_audit = require_stage_audit(self.store, 
                validated_request.operation_id,
                GovernanceStage.PLAN,
            )
            require_stage_audit(self.store, validated_request.operation_id, GovernanceStage.PREVIEW)
            selector = ConcealSelector.model_validate(plan_audit.selection)

            with self.store.transaction() as transaction:
                records = resolve_selector(selector, transaction.iter_direct_provenance())
                candidate_object_ids = [record.bound_object_id for record in records]
                candidate_provenance_ids = [record.provenance_id for record in records]
                concealed_object_ids: list[str] = []
                already_concealed_object_ids: list[str] = []
                last_parent_event_id = f"{event_prefix}-selection"
                record_telemetry(self._telemetry_recorder, enabled=execution_context.dev_mode,
                    event=TelemetryEvent(
                        event_id=last_parent_event_id,
                        scope=TelemetryScope.GOVERNANCE,
                        kind=TelemetryEventKind.DECISION,
                        occurred_at=self._clock(),
                        run_id=run_id,
                        operation_id=operation_id,
                        parent_event_id=f"{event_prefix}-entry",
                        job_id=operation_id,
                        actor=execution_context.actor,
                        payload={
                            "stage": "execute_selection",
                            "candidate_object_ids": candidate_object_ids,
                            "candidate_provenance_ids": candidate_provenance_ids,
                        },
                        debug_fields={
                            "candidate_object_count": len(candidate_object_ids),
                        },
                    ),
                )

                for index, record in enumerate(records, start=1):
                    if transaction.is_object_concealed(record.bound_object_id):
                        already_concealed_object_ids.append(record.bound_object_id)
                        continue
                    transaction.record_concealment(
                        ConcealmentRecord(
                            concealment_id=new_governance_id(
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
                        audit_id=new_audit_id(GovernanceStage.EXECUTE),
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
        except Exception as exc:
            record_telemetry(self._telemetry_recorder, enabled=execution_context.dev_mode,
                event=TelemetryEvent(
                    event_id=f"{event_prefix}-result",
                    scope=TelemetryScope.GOVERNANCE,
                    kind=TelemetryEventKind.ACTION_RESULT,
                    occurred_at=self._clock(),
                    run_id=run_id,
                    operation_id=operation_id,
                    parent_event_id=last_parent_event_id,
                    job_id=operation_id,
                    actor=execution_context.actor,
                    payload={
                        "stage": "execute",
                        "outcome": "failure",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    },
                ),
            )
            raise

        result = ConcealExecuteResult(
            operation_id=validated_request.operation_id,
            concealed_object_ids=concealed_object_ids,
            already_concealed_object_ids=already_concealed_object_ids,
        )
        record_telemetry(self._telemetry_recorder, enabled=execution_context.dev_mode,
            event=TelemetryEvent(
                event_id=f"{event_prefix}-result",
                scope=TelemetryScope.GOVERNANCE,
                kind=TelemetryEventKind.ACTION_RESULT,
                occurred_at=self._clock(),
                run_id=run_id,
                operation_id=operation_id,
                parent_event_id=last_parent_event_id,
                job_id=operation_id,
                actor=execution_context.actor,
                payload={
                    "stage": "execute",
                    "outcome": "success",
                    "result": result.model_dump(mode="json"),
                },
            ),
        )
        return result
