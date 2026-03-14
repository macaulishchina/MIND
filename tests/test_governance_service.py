from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mind.governance import GovernanceService, GovernanceServiceError
from mind.kernel.governance import GovernanceStage
from mind.kernel.provenance import HIGH_SENSITIVITY_PROVENANCE_FIELDS
from mind.kernel.store import SQLiteMemoryStore
from mind.primitives.contracts import Capability, PrimitiveExecutionContext, PrimitiveOutcome
from mind.primitives.service import PrimitiveService

FIXED_TIMESTAMP = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


def _context(
    *,
    actor: str,
    capabilities: list[Capability],
) -> PrimitiveExecutionContext:
    return PrimitiveExecutionContext(
        actor=actor,
        budget_scope_id=f"governance::{actor}",
        capabilities=capabilities,
    )


def test_governance_service_conceal_flow_records_full_audit_chain(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_h_governance_service.sqlite3"

    with SQLiteMemoryStore(db_path) as store:
        primitive_service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)
        governance_service = GovernanceService(store, clock=lambda: FIXED_TIMESTAMP)

        write_a = primitive_service.write_raw(
            {
                "record_kind": "user_message",
                "content": {"text": "alpha record from user a"},
                "episode_id": "episode-a",
                "timestamp_order": 1,
                "direct_provenance": {
                    "producer_kind": "user",
                    "producer_id": "user-a",
                    "captured_at": "2026-03-09T10:00:00+00:00",
                    "source_channel": "chat",
                    "tenant_id": "tenant-a",
                    "user_id": "user-a",
                    "ip_addr": "203.0.113.1",
                    "session_id": "session-a",
                    "episode_id": "episode-a",
                },
            },
            _context(actor="writer-a", capabilities=[Capability.MEMORY_READ]),
        )
        write_b = primitive_service.write_raw(
            {
                "record_kind": "user_message",
                "content": {"text": "beta record from user b"},
                "episode_id": "episode-b",
                "timestamp_order": 1,
                "direct_provenance": {
                    "producer_kind": "user",
                    "producer_id": "user-b",
                    "captured_at": "2026-03-09T11:00:00+00:00",
                    "source_channel": "chat",
                    "tenant_id": "tenant-a",
                    "user_id": "user-b",
                    "episode_id": "episode-b",
                },
            },
            _context(actor="writer-b", capabilities=[Capability.MEMORY_READ]),
        )

        assert write_a.response is not None
        assert write_b.response is not None

        plan = governance_service.plan_conceal(
            {
                "selector": {
                    "producer_id": "user-a",
                    "captured_after": "2026-03-09T00:00:00+00:00",
                },
                "reason": "conceal user-a material",
            },
            _context(actor="planner", capabilities=[Capability.GOVERNANCE_PLAN]),
        )
        preview = governance_service.preview_conceal(
            {"operation_id": plan.operation_id},
            _context(actor="planner", capabilities=[Capability.GOVERNANCE_PLAN]),
        )
        execute = governance_service.execute_conceal(
            {"operation_id": plan.operation_id},
            _context(actor="executor", capabilities=[Capability.GOVERNANCE_EXECUTE]),
        )

        assert plan.candidate_object_ids == [write_a.response["object_id"]]
        assert plan.candidate_provenance_ids == [write_a.response["provenance_id"]]
        assert preview.candidate_object_ids == [write_a.response["object_id"]]
        summary = preview.provenance_summaries[write_a.response["object_id"]].model_dump(
            mode="json"
        )
        assert summary["producer_id"] == "user-a"
        assert summary["user_id"] == "user-a"
        assert not (HIGH_SENSITIVITY_PROVENANCE_FIELDS & set(summary))
        assert execute.concealed_object_ids == [write_a.response["object_id"]]
        assert execute.already_concealed_object_ids == []
        assert store.is_object_concealed(write_a.response["object_id"])
        assert not store.is_object_concealed(write_b.response["object_id"])

        read_result = primitive_service.read(
            {"object_ids": [write_a.response["object_id"]]},
            _context(actor="reader", capabilities=[Capability.MEMORY_READ]),
        )
        retrieve_result = primitive_service.retrieve(
            {
                "query": "alpha record user a",
                "query_modes": ["keyword"],
                "budget": {"max_cost": 5.0, "max_candidates": 10},
                "filters": {"object_types": ["RawRecord"]},
            },
            _context(actor="reader", capabilities=[Capability.MEMORY_READ]),
        )
        audits = store.iter_governance_audit_for_operation(plan.operation_id)

    assert read_result.outcome is PrimitiveOutcome.REJECTED
    assert read_result.error is not None
    assert read_result.error.code.value == "object_inaccessible"
    assert retrieve_result.outcome is PrimitiveOutcome.SUCCESS
    assert retrieve_result.response is not None
    assert write_a.response["object_id"] not in retrieve_result.response["candidate_ids"]
    assert [audit.stage for audit in audits] == [
        GovernanceStage.PLAN,
        GovernanceStage.PREVIEW,
        GovernanceStage.EXECUTE,
    ]


def test_governance_service_execute_requires_preview(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_h_governance_service_requires_preview.sqlite3"

    with SQLiteMemoryStore(db_path) as store:
        primitive_service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)
        governance_service = GovernanceService(store, clock=lambda: FIXED_TIMESTAMP)

        write_result = primitive_service.write_raw(
            {
                "record_kind": "user_message",
                "content": {"text": "gamma record from user c"},
                "episode_id": "episode-c",
                "timestamp_order": 1,
                "direct_provenance": {
                    "producer_kind": "user",
                    "producer_id": "user-c",
                    "captured_at": "2026-03-09T12:00:00+00:00",
                    "source_channel": "chat",
                    "tenant_id": "tenant-a",
                    "user_id": "user-c",
                    "episode_id": "episode-c",
                },
            },
            _context(actor="writer-c", capabilities=[Capability.MEMORY_READ]),
        )

        assert write_result.response is not None
        plan = governance_service.plan_conceal(
            {
                "selector": {"producer_id": "user-c"},
                "reason": "conceal user-c material",
            },
            _context(actor="planner", capabilities=[Capability.GOVERNANCE_PLAN]),
        )

        with pytest.raises(GovernanceServiceError):
            governance_service.execute_conceal(
                {"operation_id": plan.operation_id},
                _context(actor="executor", capabilities=[Capability.GOVERNANCE_EXECUTE]),
            )

        assert not store.is_object_concealed(write_result.response["object_id"])


def test_governance_service_requires_governance_plan_capability(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "phase_h_governance_service_requires_plan_cap.sqlite3"

    with SQLiteMemoryStore(db_path) as store:
        governance_service = GovernanceService(store, clock=lambda: FIXED_TIMESTAMP)

        with pytest.raises(GovernanceServiceError, match="governance_plan"):
            governance_service.plan_conceal(
                {
                    "selector": {"producer_id": "user-x"},
                    "reason": "conceal without governance privilege",
                },
                _context(actor="reader", capabilities=[Capability.MEMORY_READ]),
            )
