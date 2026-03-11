from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mind.governance import GovernanceService, GovernanceServiceError
from mind.kernel.store import SQLiteMemoryStore
from mind.primitives.contracts import Capability, PrimitiveExecutionContext
from mind.primitives.service import PrimitiveService
from mind.telemetry import InMemoryTelemetryRecorder, TelemetryEventKind, TelemetryScope

FIXED_TIMESTAMP = datetime(2026, 3, 12, 2, 15, tzinfo=UTC)


def _context(
    *,
    actor: str,
    capabilities: list[Capability],
    dev_mode: bool = False,
    telemetry_run_id: str | None = None,
) -> PrimitiveExecutionContext:
    return PrimitiveExecutionContext(
        actor=actor,
        budget_scope_id=f"governance::{actor}",
        capabilities=capabilities,
        dev_mode=dev_mode,
        telemetry_run_id=telemetry_run_id,
    )


def _seed_governance_objects(
    store: SQLiteMemoryStore,
) -> tuple[dict[str, str], dict[str, str]]:
    primitive_service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)
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
    return write_a.response, write_b.response


def test_governance_conceal_flow_emits_events_in_dev_mode(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()

    with SQLiteMemoryStore(tmp_path / "phase_l_governance_flow.sqlite3") as store:
        write_a, write_b = _seed_governance_objects(store)
        service = GovernanceService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )
        plan = service.plan_conceal(
            {
                "selector": {
                    "producer_id": "user-a",
                    "captured_after": "2026-03-09T00:00:00+00:00",
                },
                "reason": "conceal user-a material",
            },
            _context(
                actor="planner",
                capabilities=[Capability.GOVERNANCE_PLAN],
                dev_mode=True,
                telemetry_run_id="run-phase-l-governance-001",
            ),
        )
        preview = service.preview_conceal(
            {"operation_id": plan.operation_id},
            _context(
                actor="planner",
                capabilities=[Capability.GOVERNANCE_PLAN],
                dev_mode=True,
                telemetry_run_id="run-phase-l-governance-001",
            ),
        )
        execute = service.execute_conceal(
            {"operation_id": plan.operation_id},
            _context(
                actor="executor",
                capabilities=[Capability.GOVERNANCE_EXECUTE],
                dev_mode=True,
                telemetry_run_id="run-phase-l-governance-001",
            ),
        )

        assert execute.concealed_object_ids == [write_a["object_id"]]
        assert execute.already_concealed_object_ids == []
        assert not store.is_object_concealed(write_b["object_id"])

    governance_events = [
        event for event in recorder.iter_events() if event.scope is TelemetryScope.GOVERNANCE
    ]
    assert len(governance_events) == 9
    assert [event.kind for event in governance_events] == [
        TelemetryEventKind.ENTRY,
        TelemetryEventKind.DECISION,
        TelemetryEventKind.ACTION_RESULT,
        TelemetryEventKind.ENTRY,
        TelemetryEventKind.DECISION,
        TelemetryEventKind.ACTION_RESULT,
        TelemetryEventKind.ENTRY,
        TelemetryEventKind.DECISION,
        TelemetryEventKind.ACTION_RESULT,
    ]
    assert all(event.run_id == "run-phase-l-governance-001" for event in governance_events)
    assert all(event.job_id == plan.operation_id for event in governance_events)
    assert governance_events[1].payload["stage"] == "plan_selection"
    assert governance_events[4].payload["stage"] == "preview_selection"
    assert governance_events[7].payload["stage"] == "execute_selection"
    assert governance_events[8].payload["result"]["concealed_object_ids"] == [write_a["object_id"]]
    assert preview.candidate_object_ids == [write_a["object_id"]]


def test_governance_execute_failure_emits_failure_result(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()

    with SQLiteMemoryStore(tmp_path / "phase_l_governance_failure.sqlite3") as store:
        _seed_governance_objects(store)
        service = GovernanceService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )
        plan = service.plan_conceal(
            {
                "selector": {"producer_id": "user-a"},
                "reason": "conceal user-a material",
            },
            _context(
                actor="planner",
                capabilities=[Capability.GOVERNANCE_PLAN],
                dev_mode=True,
                telemetry_run_id="run-phase-l-governance-002",
            ),
        )
        recorder.clear()

        with pytest.raises(GovernanceServiceError, match="missing governance preview audit"):
            service.execute_conceal(
                {"operation_id": plan.operation_id},
                _context(
                    actor="executor",
                    capabilities=[Capability.GOVERNANCE_EXECUTE],
                    dev_mode=True,
                    telemetry_run_id="run-phase-l-governance-002",
                ),
            )

    governance_events = [
        event for event in recorder.iter_events() if event.scope is TelemetryScope.GOVERNANCE
    ]
    assert [event.kind for event in governance_events] == [
        TelemetryEventKind.ENTRY,
        TelemetryEventKind.ACTION_RESULT,
    ]
    assert governance_events[-1].payload["stage"] == "execute"
    assert governance_events[-1].payload["outcome"] == "failure"
    assert governance_events[-1].payload["error_type"] == "GovernanceServiceError"


def test_governance_telemetry_is_disabled_when_dev_mode_false(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()

    with SQLiteMemoryStore(tmp_path / "phase_l_governance_disabled.sqlite3") as store:
        _seed_governance_objects(store)
        service = GovernanceService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )
        service.plan_conceal(
            {
                "selector": {"producer_id": "user-a"},
                "reason": "conceal user-a material",
            },
            _context(actor="planner", capabilities=[Capability.GOVERNANCE_PLAN]),
        )

    assert [
        event for event in recorder.iter_events() if event.scope is TelemetryScope.GOVERNANCE
    ] == []
