from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from mind.kernel.governance import (
    GovernanceAction,
    GovernanceAuditRecord,
    GovernanceCapability,
    GovernanceOutcome,
    GovernanceScope,
    GovernanceStage,
)
from mind.kernel.store import SQLiteMemoryStore

FIXED_TIMESTAMP = datetime(2026, 3, 10, 10, 0, tzinfo=UTC)


def test_governance_audit_round_trip_in_sqlite_store(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_h_governance_audit.sqlite3"

    records = [
        GovernanceAuditRecord(
            audit_id="audit-plan-001",
            operation_id="op-001",
            action=GovernanceAction.CONCEAL,
            stage=GovernanceStage.PLAN,
            actor="governance-operator",
            capability=GovernanceCapability.GOVERNANCE_PLAN,
            timestamp=FIXED_TIMESTAMP,
            outcome=GovernanceOutcome.SUCCEEDED,
            target_object_ids=["raw-001", "raw-002"],
            target_provenance_ids=["prov-001", "prov-002"],
            selection={"producer_id": "user-a", "captured_after": "2026-03-01T00:00:00+00:00"},
            summary={"candidate_object_count": 2},
        ),
        GovernanceAuditRecord(
            audit_id="audit-preview-001",
            operation_id="op-001",
            action=GovernanceAction.CONCEAL,
            stage=GovernanceStage.PREVIEW,
            actor="governance-operator",
            capability=GovernanceCapability.GOVERNANCE_PLAN,
            timestamp=FIXED_TIMESTAMP.replace(minute=5),
            outcome=GovernanceOutcome.SUCCEEDED,
            target_object_ids=["raw-001", "raw-002"],
            target_provenance_ids=["prov-001", "prov-002"],
            selection={"producer_id": "user-a", "captured_after": "2026-03-01T00:00:00+00:00"},
            summary={"candidate_object_count": 2, "workspace_impact": 1},
        ),
        GovernanceAuditRecord(
            audit_id="audit-execute-001",
            operation_id="op-001",
            action=GovernanceAction.CONCEAL,
            stage=GovernanceStage.EXECUTE,
            actor="governance-operator",
            capability=GovernanceCapability.GOVERNANCE_EXECUTE,
            timestamp=FIXED_TIMESTAMP.replace(minute=10),
            outcome=GovernanceOutcome.SUCCEEDED,
            reason="operator requested targeted conceal",
            target_object_ids=["raw-001", "raw-002"],
            target_provenance_ids=["prov-001", "prov-002"],
            selection={"producer_id": "user-a", "captured_after": "2026-03-01T00:00:00+00:00"},
            summary={"concealed_object_count": 2},
        ),
    ]

    with SQLiteMemoryStore(db_path) as store:
        for record in records:
            store.record_governance_audit(record)

        fetched = store.read_governance_audit("audit-preview-001")
        operation_rows = store.iter_governance_audit_for_operation("op-001")
        all_rows = store.iter_governance_audit()

    assert fetched.audit_id == "audit-preview-001"
    assert fetched.stage.value == "preview"
    assert fetched.summary["workspace_impact"] == 1
    assert [row.audit_id for row in operation_rows] == [
        "audit-plan-001",
        "audit-preview-001",
        "audit-execute-001",
    ]
    assert len(all_rows) == 3
    assert all_rows[-1].reason == "operator requested targeted conceal"


def test_governance_audit_enforces_approval_contract() -> None:
    with pytest.raises(ValidationError):
        GovernanceAuditRecord(
            audit_id="audit-approve-invalid",
            operation_id="op-erase",
            action=GovernanceAction.ERASE,
            stage=GovernanceStage.APPROVE,
            actor="approver-a",
            capability=GovernanceCapability.GOVERNANCE_EXECUTE,
            timestamp=FIXED_TIMESTAMP,
            outcome=GovernanceOutcome.SUCCEEDED,
            scope=GovernanceScope.FULL,
        )

    with pytest.raises(ValidationError):
        GovernanceAuditRecord(
            audit_id="audit-approve-nonfull",
            operation_id="op-erase",
            action=GovernanceAction.ERASE,
            stage=GovernanceStage.APPROVE,
            actor="approver-a",
            capability=GovernanceCapability.GOVERNANCE_APPROVE_FULL_ERASE,
            timestamp=FIXED_TIMESTAMP,
            outcome=GovernanceOutcome.SUCCEEDED,
            scope=GovernanceScope.MEMORY_WORLD,
        )
