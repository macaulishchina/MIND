"""Supplementary Phase H tests added during independent audit.

Coverage targets:
- DEF-1-validate: pyproject.toml script entry exists
- Duplicate provenance rejection (H-2 integrity)
- ConcealSelector empty-selector Pydantic rejection
- Double governance execute idempotency
- Preview-without-plan governance rejection
- Provenance for missing object rejection
- ProvenanceSummary field isolation contract
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from mind.governance import GovernanceService, GovernanceServiceError
from mind.kernel.governance import (
    ConcealSelector,
    GovernanceAction,
    GovernanceAuditRecord,
    GovernanceCapability,
    GovernanceOutcome,
    GovernanceScope,
    GovernanceStage,
)
from mind.kernel.provenance import (
    HIGH_SENSITIVITY_PROVENANCE_FIELDS,
    DirectProvenanceRecord,
    ProducerKind,
    ProvenanceSummary,
    RetentionClass,
    SourceChannel,
    build_provenance_summary,
)
from mind.kernel.store import SQLiteMemoryStore, StoreError
from mind.primitives.contracts import Capability, PrimitiveExecutionContext
from mind.primitives.service import PrimitiveService

FIXED_TIMESTAMP = datetime(2026, 3, 10, 15, 0, tzinfo=UTC)


def _context(
    *,
    actor: str = "audit-tester",
    capabilities: list[Capability] | None = None,
) -> PrimitiveExecutionContext:
    return PrimitiveExecutionContext(
        actor=actor,
        budget_scope_id=f"audit::{actor}",
        budget_limit=50.0,
        capabilities=capabilities or [Capability.MEMORY_READ],
    )


# ---------------------------------------------------------------------------
# DEF-1-validate: pyproject.toml script entry exists
# ---------------------------------------------------------------------------
def test_pyproject_contains_phase_h_gate_entry() -> None:
    """DEF-1 regression: the renamed Phase H gate entry must be registered."""
    import tomllib

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    scripts = data.get("project", {}).get("scripts", {})
    assert "mindtest-phase-h-gate" in scripts, (
        "pyproject.toml is missing mindtest-phase-h-gate script entry"
    )
    assert scripts["mindtest-phase-h-gate"] == "mind.cli:governance_gate_main"


# ---------------------------------------------------------------------------
# Duplicate provenance rejection (H-2 integrity)
# ---------------------------------------------------------------------------
def test_duplicate_direct_provenance_for_same_object_rejected(tmp_path: Path) -> None:
    """Second direct provenance for the same bound object must fail."""
    db_path = tmp_path / "audit_dup_provenance.sqlite3"
    with SQLiteMemoryStore(db_path) as store:
        service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)
        result = service.write_raw(
            {
                "record_kind": "user_message",
                "content": {"text": "audit dup provenance"},
                "episode_id": "ep-dup",
                "timestamp_order": 1,
            },
            _context(actor="writer"),
        )
        assert result.response is not None
        object_id = result.response["object_id"]
        provenance = store.direct_provenance_for_object(object_id)

        duplicate_record = DirectProvenanceRecord(
            provenance_id="dup-provenance-id",
            bound_object_id=object_id,
            bound_object_type="RawRecord",
            producer_kind=provenance.producer_kind,
            producer_id=provenance.producer_id,
            captured_at=provenance.captured_at,
            ingested_at=FIXED_TIMESTAMP,
            source_channel=provenance.source_channel,
            tenant_id=provenance.tenant_id,
            retention_class=provenance.retention_class,
            episode_id="ep-dup",
        )
        with pytest.raises(StoreError, match="already exists"):
            store.insert_direct_provenance(duplicate_record)


# ---------------------------------------------------------------------------
# ConcealSelector empty-selector Pydantic rejection
# ---------------------------------------------------------------------------
def test_conceal_selector_rejects_empty_filter() -> None:
    """ConcealSelector with no filter criteria must fail validation."""
    with pytest.raises(ValidationError, match="at least one"):
        ConcealSelector()


# ---------------------------------------------------------------------------
# Double governance execute idempotency
# ---------------------------------------------------------------------------
def test_double_execute_reports_already_concealed(tmp_path: Path) -> None:
    """Executing the same conceal operation twice should be idempotent."""
    db_path = tmp_path / "audit_double_execute.sqlite3"
    with SQLiteMemoryStore(db_path) as store:
        service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)
        gov = GovernanceService(store, clock=lambda: FIXED_TIMESTAMP)

        result = service.write_raw(
            {
                "record_kind": "user_message",
                "content": {"text": "audit double execute"},
                "episode_id": "ep-dblx",
                "timestamp_order": 1,
            },
            _context(actor="writer"),
        )
        assert result.response is not None
        object_id = result.response["object_id"]

        plan_ctx = _context(actor="planner", capabilities=[Capability.GOVERNANCE_PLAN])
        exec_ctx = _context(actor="executor", capabilities=[Capability.GOVERNANCE_EXECUTE])

        plan = gov.plan_conceal(
            {"selector": {"object_ids": [object_id]}, "reason": "first conceal"},
            plan_ctx,
        )
        gov.preview_conceal({"operation_id": plan.operation_id}, plan_ctx)
        first_exec = gov.execute_conceal({"operation_id": plan.operation_id}, exec_ctx)
        assert first_exec.concealed_object_ids == [object_id]
        assert first_exec.already_concealed_object_ids == []

        plan2 = gov.plan_conceal(
            {"selector": {"object_ids": [object_id]}, "reason": "second conceal"},
            plan_ctx,
        )
        gov.preview_conceal({"operation_id": plan2.operation_id}, plan_ctx)
        second_exec = gov.execute_conceal({"operation_id": plan2.operation_id}, exec_ctx)
        assert second_exec.concealed_object_ids == []
        assert second_exec.already_concealed_object_ids == [object_id]


# ---------------------------------------------------------------------------
# Preview-without-plan governance rejection
# ---------------------------------------------------------------------------
def test_preview_without_plan_rejected(tmp_path: Path) -> None:
    """Previewing a non-existent conceal operation must fail."""
    db_path = tmp_path / "audit_preview_no_plan.sqlite3"
    with SQLiteMemoryStore(db_path) as store:
        gov = GovernanceService(store, clock=lambda: FIXED_TIMESTAMP)
        plan_ctx = _context(actor="planner", capabilities=[Capability.GOVERNANCE_PLAN])

        with pytest.raises(GovernanceServiceError, match="missing governance plan"):
            gov.preview_conceal(
                {"operation_id": "nonexistent-op"},
                plan_ctx,
            )


# ---------------------------------------------------------------------------
# Provenance for missing object rejection
# ---------------------------------------------------------------------------
def test_provenance_for_missing_object_rejected(tmp_path: Path) -> None:
    """Direct provenance bound to a nonexistent object must fail."""
    db_path = tmp_path / "audit_prov_missing.sqlite3"
    with SQLiteMemoryStore(db_path) as store:
        record = DirectProvenanceRecord(
            provenance_id="prov-orphan",
            bound_object_id="nonexistent-obj",
            bound_object_type="RawRecord",
            producer_kind=ProducerKind.SYSTEM,
            producer_id="test",
            captured_at=FIXED_TIMESTAMP,
            ingested_at=FIXED_TIMESTAMP,
            source_channel=SourceChannel.SYSTEM_INTERNAL,
            tenant_id="default",
            retention_class=RetentionClass.DEFAULT,
        )
        with pytest.raises(StoreError, match="missing object"):
            store.insert_direct_provenance(record)


# ---------------------------------------------------------------------------
# ProvenanceSummary field isolation contract
# ---------------------------------------------------------------------------
def test_provenance_summary_excludes_all_high_sensitivity_fields() -> None:
    """ProvenanceSummary must structurally exclude every HIGH_SENSITIVITY field."""
    summary_fields = set(ProvenanceSummary.model_fields.keys())
    overlap = HIGH_SENSITIVITY_PROVENANCE_FIELDS & summary_fields
    assert overlap == set(), f"ProvenanceSummary leaks high-sensitivity fields: {overlap}"


def test_build_provenance_summary_strips_high_sensitivity() -> None:
    """build_provenance_summary must not propagate any high-sensitivity value."""
    record = DirectProvenanceRecord(
        provenance_id="prov-strip",
        bound_object_id="obj-strip",
        bound_object_type="RawRecord",
        producer_kind=ProducerKind.USER,
        producer_id="user-strip",
        captured_at=FIXED_TIMESTAMP,
        ingested_at=FIXED_TIMESTAMP,
        source_channel=SourceChannel.CHAT,
        tenant_id="default",
        retention_class=RetentionClass.DEFAULT,
        ip_addr="10.0.0.1",
        device_id="device-strip",
        machine_fingerprint="fp-strip",
        session_id="session-strip",
        request_id="request-strip",
        conversation_id="conversation-strip",
    )
    summary = build_provenance_summary(record)
    payload = summary.model_dump(mode="json")
    leaked = HIGH_SENSITIVITY_PROVENANCE_FIELDS & set(payload.keys())
    assert leaked == set(), f"summary leaked: {leaked}"
    assert payload["producer_id"] == "user-strip"


# ---------------------------------------------------------------------------
# GovernanceAuditRecord scope contract (approve requires full + erase)
# ---------------------------------------------------------------------------
def test_approve_stage_valid_only_with_erase_full() -> None:
    """GovernanceAuditRecord approve stage requires erase action + full scope."""
    valid = GovernanceAuditRecord(
        audit_id="audit-approve-ok",
        operation_id="op-erase-ok",
        action=GovernanceAction.ERASE,
        stage=GovernanceStage.APPROVE,
        actor="approver",
        capability=GovernanceCapability.GOVERNANCE_APPROVE_FULL_ERASE,
        timestamp=FIXED_TIMESTAMP,
        outcome=GovernanceOutcome.SUCCEEDED,
        scope=GovernanceScope.FULL,
    )
    assert valid.stage == GovernanceStage.APPROVE

    with pytest.raises(ValidationError):
        GovernanceAuditRecord(
            audit_id="audit-approve-bad-action",
            operation_id="op-conceal-approve",
            action=GovernanceAction.CONCEAL,
            stage=GovernanceStage.APPROVE,
            actor="approver",
            capability=GovernanceCapability.GOVERNANCE_APPROVE_FULL_ERASE,
            timestamp=FIXED_TIMESTAMP,
            outcome=GovernanceOutcome.SUCCEEDED,
            scope=GovernanceScope.FULL,
        )
