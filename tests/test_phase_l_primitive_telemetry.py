from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mind.fixtures.golden_episode_set import build_core_object_showcase
from mind.kernel.store import SQLiteMemoryStore
from mind.primitives.contracts import Capability, PrimitiveExecutionContext, PrimitiveOutcome
from mind.primitives.service import PrimitiveService
from mind.telemetry import InMemoryTelemetryRecorder, TelemetryEventKind, TelemetryScope

FIXED_TIMESTAMP = datetime(2026, 3, 11, 23, 30, tzinfo=UTC)


def _context(
    *,
    dev_mode: bool = False,
    budget_limit: float | None = 100.0,
    telemetry_run_id: str | None = None,
    telemetry_operation_id: str | None = None,
    telemetry_parent_event_id: str | None = None,
) -> PrimitiveExecutionContext:
    return PrimitiveExecutionContext(
        actor="phase-l-tester",
        budget_scope_id="phase-l-smoke",
        budget_limit=budget_limit,
        capabilities=[Capability.MEMORY_READ],
        dev_mode=dev_mode,
        telemetry_run_id=telemetry_run_id,
        telemetry_operation_id=telemetry_operation_id,
        telemetry_parent_event_id=telemetry_parent_event_id,
    )


def test_primitive_telemetry_is_disabled_by_default(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()

    with SQLiteMemoryStore(tmp_path / "phase_l_telemetry_default.sqlite3") as store:
        service = PrimitiveService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )

        result = service.write_raw(
            {
                "record_kind": "user_message",
                "content": {"text": "no telemetry please"},
                "episode_id": "episode-l-default",
                "timestamp_order": 1,
            },
            _context(),
        )

        assert result.outcome is PrimitiveOutcome.SUCCESS
        assert tuple(recorder.iter_events()) == ()


def test_write_raw_emits_primitive_and_object_delta_events_in_dev_mode(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()

    with SQLiteMemoryStore(tmp_path / "phase_l_telemetry_write.sqlite3") as store:
        service = PrimitiveService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )

        result = service.write_raw(
            {
                "record_kind": "assistant_message",
                "content": {"text": "emit telemetry"},
                "episode_id": "episode-l-write",
                "timestamp_order": 1,
            },
            _context(dev_mode=True, telemetry_run_id="run-phase-l-001"),
        )

        assert result.outcome is PrimitiveOutcome.SUCCESS
        events = tuple(recorder.iter_events())
        assert len(events) == 3
        assert [event.scope for event in events] == [
            TelemetryScope.PRIMITIVE,
            TelemetryScope.PRIMITIVE,
            TelemetryScope.OBJECT_DELTA,
        ]
        assert [event.kind for event in events] == [
            TelemetryEventKind.ENTRY,
            TelemetryEventKind.ACTION_RESULT,
            TelemetryEventKind.STATE_DELTA,
        ]
        assert all(event.run_id == "run-phase-l-001" for event in events)
        assert events[0].payload["primitive"] == "write_raw"
        assert result.response is not None
        assert events[1].debug_fields["mutated_ids"] == [result.response["object_id"]]
        assert events[2].object_id == result.response["object_id"]
        assert events[2].object_version == 1
        assert events[2].before == {}
        assert events[2].after is not None
        assert events[2].after["version"] == 1
        assert events[2].delta is not None
        assert events[2].delta["version"]["before"] is None
        assert events[2].delta["version"]["after"] == 1
        assert events[2].debug_fields["created"] is True


def test_primitive_context_can_override_operation_and_parent_ids(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()

    with SQLiteMemoryStore(tmp_path / "phase_l_telemetry_parent_chain.sqlite3") as store:
        service = PrimitiveService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )

        result = service.write_raw(
            {
                "record_kind": "assistant_message",
                "content": {"text": "parent chain"},
                "episode_id": "episode-l-chain",
                "timestamp_order": 1,
            },
            _context(
                dev_mode=True,
                telemetry_run_id="run-phase-l-chain-001",
                telemetry_operation_id="outer-op-001",
                telemetry_parent_event_id="outer-op-001-entry",
            ),
        )

    assert result.outcome is PrimitiveOutcome.SUCCESS
    events = tuple(recorder.iter_events())
    primitive_entry = next(
        event
        for event in events
        if event.scope is TelemetryScope.PRIMITIVE and event.kind is TelemetryEventKind.ENTRY
    )
    assert primitive_entry.operation_id == "outer-op-001"
    assert primitive_entry.parent_event_id == "outer-op-001-entry"
    object_delta = next(event for event in events if event.scope is TelemetryScope.OBJECT_DELTA)
    assert object_delta.operation_id == "outer-op-001"


def test_reorganize_simple_emits_state_delta_with_previous_version(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()
    showcase = build_core_object_showcase()

    with SQLiteMemoryStore(tmp_path / "phase_l_telemetry_reorganize.sqlite3") as store:
        store.insert_objects(showcase)
        service = PrimitiveService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )

        result = service.reorganize_simple(
            {
                "target_refs": [showcase[2]["id"]],
                "operation": "archive",
                "reason": "phase l archive telemetry",
            },
            _context(dev_mode=True, telemetry_run_id="run-phase-l-002"),
        )

        assert result.outcome is PrimitiveOutcome.SUCCESS
        delta_event = next(
            event for event in recorder.iter_events() if event.scope is TelemetryScope.OBJECT_DELTA
        )
        assert delta_event.before is not None
        assert delta_event.object_id == showcase[2]["id"]
        assert delta_event.object_version == 2
        assert delta_event.before["version"] == 1
        assert delta_event.before["status"] == "active"
        assert delta_event.after is not None
        assert delta_event.after["version"] == 2
        assert delta_event.after["status"] == "archived"
        assert delta_event.delta is not None
        assert delta_event.delta["status"] == {
            "before": "active",
            "after": "archived",
        }
        assert delta_event.debug_fields["created"] is False


def test_budget_rejection_emits_decision_without_object_delta(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()

    with SQLiteMemoryStore(tmp_path / "phase_l_telemetry_budget.sqlite3") as store:
        service = PrimitiveService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )

        result = service.write_raw(
            {
                "record_kind": "user_message",
                "content": {"text": "this will exceed budget"},
                "episode_id": "episode-l-budget",
                "timestamp_order": 1,
            },
            _context(dev_mode=True, budget_limit=0.1, telemetry_run_id="run-phase-l-003"),
        )

        assert result.outcome is PrimitiveOutcome.REJECTED
        events = tuple(recorder.iter_events())
        assert len(events) == 2
        assert events[0].kind is TelemetryEventKind.ENTRY
        assert events[1].kind is TelemetryEventKind.DECISION
        assert events[1].debug_fields["error_code"] == "budget_exhausted"
        assert all(event.scope is not TelemetryScope.OBJECT_DELTA for event in events)


def test_retrieve_emits_retrieval_events_for_store_search_backend(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()
    showcase = build_core_object_showcase()

    with SQLiteMemoryStore(tmp_path / "phase_l_telemetry_retrieve.sqlite3") as store:
        store.insert_objects(showcase)
        service = PrimitiveService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )

        result = service.retrieve(
            {
                "query": "showcase summary",
                "query_modes": ["keyword"],
                "budget": {"max_cost": 5.0, "max_candidates": 3},
                "filters": {"object_types": ["SummaryNote"]},
            },
            _context(dev_mode=True, telemetry_run_id="run-phase-l-004"),
        )

        assert result.outcome is PrimitiveOutcome.SUCCESS
        retrieval_events = [
            event for event in recorder.iter_events() if event.scope is TelemetryScope.RETRIEVAL
        ]
        assert len(retrieval_events) == 3
        assert [event.kind for event in retrieval_events] == [
            TelemetryEventKind.ENTRY,
            TelemetryEventKind.DECISION,
            TelemetryEventKind.ACTION_RESULT,
        ]
        assert retrieval_events[0].payload["query_modes"] == ["keyword"]
        assert retrieval_events[1].payload["retrieval_backend"] == "store_search"
        assert retrieval_events[1].payload["candidate_ids"]
        assert retrieval_events[2].payload["evidence_summary"]["returned_count"] >= 1
        assert result.response is not None
        assert (
            retrieval_events[2].debug_fields["top_candidate_id"]
            == result.response["candidate_ids"][0]
        )


def test_retrieve_emits_retrieval_events_for_vector_override_backend(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()
    showcase = build_core_object_showcase()

    def vector_retriever(
        query: str | dict[str, object], objects: list[dict[str, object]]
    ) -> dict[str, float]:
        return {str(obj["id"]): (1.0 if obj["type"] == "SummaryNote" else 0.0) for obj in objects}

    with SQLiteMemoryStore(tmp_path / "phase_l_telemetry_retrieve_vector.sqlite3") as store:
        store.insert_objects(showcase)
        service = PrimitiveService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
            vector_retriever=vector_retriever,
        )

        result = service.retrieve(
            {
                "query": "showcase",
                "query_modes": ["keyword", "vector"],
                "budget": {"max_cost": 5.0, "max_candidates": 5},
                "filters": {"object_types": ["SummaryNote", "TaskEpisode"]},
            },
            _context(dev_mode=True, telemetry_run_id="run-phase-l-005"),
        )

        assert result.outcome is PrimitiveOutcome.SUCCESS
        decision_event = next(
            event
            for event in recorder.iter_events()
            if event.scope is TelemetryScope.RETRIEVAL and event.kind is TelemetryEventKind.DECISION
        )
        assert decision_event.payload["retrieval_backend"] == "legacy_vector_override"
        assert decision_event.debug_fields["used_vector_override"] is True
        assert decision_event.payload["candidate_scores"]
