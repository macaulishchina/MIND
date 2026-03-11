from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mind.access import AccessService
from mind.fixtures.retrieval_benchmark import build_canonical_seed_objects
from mind.kernel.store import SQLiteMemoryStore
from mind.primitives.contracts import Capability, PrimitiveExecutionContext
from mind.telemetry import InMemoryTelemetryRecorder, TelemetryEventKind, TelemetryScope

FIXED_TIMESTAMP = datetime(2026, 3, 12, 0, 45, tzinfo=UTC)


def _context(
    *,
    actor: str = "phase-l-access",
    dev_mode: bool = False,
    telemetry_run_id: str | None = None,
) -> PrimitiveExecutionContext:
    return PrimitiveExecutionContext(
        actor=actor,
        budget_scope_id=f"phase-l::{actor}",
        budget_limit=100.0,
        capabilities=[Capability.MEMORY_READ],
        dev_mode=dev_mode,
        telemetry_run_id=telemetry_run_id,
    )


def test_access_flash_run_emits_access_events_in_dev_mode(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()

    with SQLiteMemoryStore(tmp_path / "phase_l_access_flash.sqlite3") as store:
        store.insert_objects(build_canonical_seed_objects())
        service = AccessService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )

        result = service.run(
            {
                "requested_mode": "flash",
                "task_id": "task-004",
                "query": "Episode 4 revised corrected replay hints",
                "query_modes": ["keyword"],
                "filters": {"object_types": ["SummaryNote"]},
            },
            _context(dev_mode=True, telemetry_run_id="run-phase-l-access-001"),
        )

    access_events = [
        event for event in recorder.iter_events() if event.scope is TelemetryScope.ACCESS
    ]
    assert [event.kind for event in access_events] == [
        TelemetryEventKind.ENTRY,
        TelemetryEventKind.DECISION,
        TelemetryEventKind.CONTEXT_RESULT,
        TelemetryEventKind.ACTION_RESULT,
    ]
    assert all(event.run_id == "run-phase-l-access-001" for event in access_events)
    assert access_events[0].payload["requested_mode"] == "flash"
    assert access_events[1].payload["mode"] == "flash"
    assert access_events[1].payload["reason_code"] == "explicit_mode_request"
    assert access_events[2].payload["context_kind"] == "raw_topk"
    assert access_events[2].payload["context_object_ids"] == result.context_object_ids
    assert access_events[3].payload["resolved_mode"] == "flash"
    primitive_related = [
        event
        for event in recorder.iter_events()
        if event.scope in {TelemetryScope.PRIMITIVE, TelemetryScope.RETRIEVAL}
    ]
    assert primitive_related
    assert all(event.operation_id == "access-task-004" for event in primitive_related)
    primitive_entry = next(
        event
        for event in primitive_related
        if event.scope is TelemetryScope.PRIMITIVE and event.kind is TelemetryEventKind.ENTRY
    )
    assert primitive_entry.parent_event_id == "access-task-004-entry"


def test_access_auto_upgrade_emits_multiple_decision_events(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()

    with SQLiteMemoryStore(tmp_path / "phase_l_access_auto.sqlite3") as store:
        store.insert_objects(build_canonical_seed_objects())
        service = AccessService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )

        result = service.run(
            {
                "requested_mode": "auto",
                "task_id": "task-004",
                "task_family": "speed_sensitive",
                "time_budget_ms": 150,
                "hard_constraints": ["must include the latest episode summary"],
                "query": "Episode 4 revised corrected replay hints",
                "query_modes": ["keyword"],
                "filters": {"object_types": ["SummaryNote", "TaskEpisode"]},
            },
            _context(actor="phase-l-access-auto", dev_mode=True, telemetry_run_id="run-phase-l-access-002"),
        )

    access_decisions = [
        event
        for event in recorder.iter_events()
        if event.scope is TelemetryScope.ACCESS and event.kind is TelemetryEventKind.DECISION
    ]
    assert len(access_decisions) == 2
    assert [event.payload["mode"] for event in access_decisions] == ["flash", "recall"]
    assert [event.payload["switch_kind"] for event in access_decisions] == ["initial", "upgrade"]
    assert access_decisions[1].payload["reason_code"] == "constraint_risk"

    context_event = next(
        event
        for event in recorder.iter_events()
        if event.scope is TelemetryScope.ACCESS and event.kind is TelemetryEventKind.CONTEXT_RESULT
    )
    assert context_event.payload["context_kind"] == "workspace"
    assert context_event.payload["selected_object_ids"] == result.selected_object_ids


def test_access_telemetry_is_disabled_when_dev_mode_is_false(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()

    with SQLiteMemoryStore(tmp_path / "phase_l_access_off.sqlite3") as store:
        store.insert_objects(build_canonical_seed_objects())
        service = AccessService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )

        service.run(
            {
                "requested_mode": "flash",
                "task_id": "task-001",
                "query": "Episode 1 succeeded with concise replay cues",
                "query_modes": ["keyword"],
                "filters": {"object_types": ["SummaryNote"]},
            },
            _context(),
        )

    assert [
        event for event in recorder.iter_events() if event.scope is TelemetryScope.ACCESS
    ] == []
