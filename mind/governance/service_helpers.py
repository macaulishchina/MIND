"""Internal helpers for governance service workflows."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import uuid4

from mind.kernel.governance import (
    ConcealSelector,
    GovernanceAction,
    GovernanceAuditRecord,
    GovernanceStage,
)
from mind.kernel.provenance import DirectProvenanceRecord
from mind.kernel.store import MemoryStore
from mind.primitives.contracts import Capability, PrimitiveExecutionContext
from mind.telemetry import TelemetryEvent, TelemetryRecorder


class GovernanceServiceError(RuntimeError):
    """Raised when a governance workflow cannot be executed safely."""


def require_stage_audit(
    store: MemoryStore,
    operation_id: str,
    stage: GovernanceStage,
) -> GovernanceAuditRecord:
    rows = store.iter_governance_audit_for_operation(operation_id)
    matches = [
        row for row in rows if row.stage == stage and row.action == GovernanceAction.CONCEAL
    ]
    if not matches:
        raise GovernanceServiceError(
            f"conceal operation '{operation_id}' missing governance {stage.value} audit"
        )
    return matches[-1]


def resolve_selector(
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


def require_capability(
    context: PrimitiveExecutionContext,
    capability: Capability,
    *,
    action: str,
) -> None:
    if capability in context.capabilities:
        return
    raise GovernanceServiceError(f"capability '{capability.value}' required to {action}")


def new_governance_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def new_audit_id(stage: GovernanceStage) -> str:
    stage_prefix = {
        GovernanceStage.PLAN: "01-plan",
        GovernanceStage.PREVIEW: "02-preview",
        GovernanceStage.EXECUTE: "03-execute",
        GovernanceStage.APPROVE: "04-approve",
    }[stage]
    return new_governance_id(f"gov-audit-{stage_prefix}")


def record_telemetry(
    recorder: TelemetryRecorder | None,
    *,
    enabled: bool,
    event: TelemetryEvent,
) -> None:
    if enabled and recorder is not None:
        recorder.record(event)


def utc_now() -> datetime:
    return datetime.now(tz=UTC)
