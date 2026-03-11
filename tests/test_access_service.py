from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mind.access import (
    AccessContextKind,
    AccessMode,
    AccessReasonCode,
    AccessService,
    AccessServiceError,
    AccessSwitchKind,
    AccessTraceKind,
)
from mind.fixtures.retrieval_benchmark import build_canonical_seed_objects
from mind.kernel.store import SQLiteMemoryStore
from mind.primitives.contracts import Capability, PrimitiveExecutionContext

FIXED_TIMESTAMP = datetime(2026, 3, 10, 15, 0, tzinfo=UTC)


def _context(
    *,
    actor: str = "phase-i-runner",
    budget_limit: float = 50.0,
) -> PrimitiveExecutionContext:
    return PrimitiveExecutionContext(
        actor=actor,
        budget_scope_id=f"phase-i::{actor}",
        budget_limit=budget_limit,
        capabilities=[Capability.MEMORY_READ],
    )


def test_flash_mode_returns_raw_topk_context_and_minimal_trace(tmp_path: Path) -> None:
    with SQLiteMemoryStore(tmp_path / "phase_i_flash.sqlite3") as store:
        _seed_store(store)
        service = AccessService(store, clock=lambda: FIXED_TIMESTAMP)

        result = service.run(
            {
                "requested_mode": "flash",
                "task_id": "task-004",
                "query": "Episode 4 revised corrected replay hints",
                "query_modes": ["keyword"],
                "filters": {"object_types": ["SummaryNote"]},
            },
            _context(),
        )

    assert result.resolved_mode is AccessMode.FLASH
    assert result.context_kind is AccessContextKind.RAW_TOPK
    assert len(result.context_object_ids) == 1
    assert result.selected_object_ids == []
    assert [event.event_kind for event in result.trace.events] == [
        AccessTraceKind.SELECT_MODE,
        AccessTraceKind.RETRIEVE,
        AccessTraceKind.READ,
        AccessTraceKind.MODE_SUMMARY,
    ]


def test_recall_mode_builds_workspace_context(tmp_path: Path) -> None:
    with SQLiteMemoryStore(tmp_path / "phase_i_recall.sqlite3") as store:
        _seed_store(store)
        service = AccessService(store, clock=lambda: FIXED_TIMESTAMP)

        result = service.run(
            {
                "requested_mode": "recall",
                "task_id": "task-004",
                "query": "Episode 4 revised corrected replay hints",
                "query_modes": ["keyword"],
                "filters": {"object_types": ["SummaryNote", "TaskEpisode"]},
            },
            _context(),
        )

    assert result.resolved_mode is AccessMode.RECALL
    assert result.context_kind is AccessContextKind.WORKSPACE
    assert result.selected_object_ids
    assert result.candidate_summaries
    assert result.candidate_summaries[0]["object_id"] == result.candidate_ids[0]
    assert "content_preview" in result.candidate_summaries[0]
    assert result.selected_summaries
    assert result.selected_summaries[0]["object_id"] == result.selected_object_ids[0]
    assert any(event.event_kind is AccessTraceKind.WORKSPACE for event in result.trace.events)


def test_reconstruct_mode_expands_source_refs(tmp_path: Path) -> None:
    with SQLiteMemoryStore(tmp_path / "phase_i_reconstruct.sqlite3") as store:
        _seed_store(store)
        service = AccessService(store, clock=lambda: FIXED_TIMESTAMP)

        result = service.run(
            {
                "requested_mode": "reconstruct",
                "task_id": "task-004",
                "query": "Episode 4 revised corrected replay hints",
                "query_modes": ["keyword"],
                "filters": {"object_types": ["SummaryNote", "TaskEpisode", "RawRecord"]},
            },
            _context(),
        )

    assert result.resolved_mode is AccessMode.RECONSTRUCT
    assert result.expanded_object_ids
    assert sum(event.event_kind is AccessTraceKind.READ for event in result.trace.events) == 2
    assert result.context_kind is AccessContextKind.WORKSPACE


def test_reflective_mode_adds_verification_trace_and_notes(tmp_path: Path) -> None:
    with SQLiteMemoryStore(tmp_path / "phase_i_reflective.sqlite3") as store:
        _seed_store(store)
        service = AccessService(store, clock=lambda: FIXED_TIMESTAMP)

        result = service.run(
            {
                "requested_mode": "reflective_access",
                "task_id": "task-008",
                "query": "Episode 8 stale memory revalidated",
                "query_modes": ["keyword"],
                "filters": {
                    "object_types": ["ReflectionNote", "SummaryNote", "TaskEpisode", "RawRecord"]
                },
            },
            _context(),
        )

    assert result.resolved_mode is AccessMode.REFLECTIVE_ACCESS
    assert result.verification_notes
    assert any(event.event_kind is AccessTraceKind.VERIFY for event in result.trace.events)
    assert result.context_kind is AccessContextKind.WORKSPACE


def test_fixed_mode_requests_remain_locked(tmp_path: Path) -> None:
    with SQLiteMemoryStore(tmp_path / "phase_i_invalid.sqlite3") as store:
        _seed_store(store)
        service = AccessService(store, clock=lambda: FIXED_TIMESTAMP)

        result = service.run(
            {
                "requested_mode": "recall",
                "task_id": "task-001",
                "query": "Episode 1 succeeded with concise replay cues",
                "query_modes": ["keyword"],
                "filters": {"object_types": ["SummaryNote", "TaskEpisode"]},
            },
            _context(),
        )

    assert result.resolved_mode is AccessMode.RECALL
    assert (
        sum(event.event_kind is AccessTraceKind.SELECT_MODE for event in result.trace.events)
        == 1
    )


def test_auto_upgrades_from_flash_to_recall_when_constraints_require_more_context(
    tmp_path: Path,
) -> None:
    with SQLiteMemoryStore(tmp_path / "phase_i_auto_upgrade.sqlite3") as store:
        _seed_store(store)
        service = AccessService(store, clock=lambda: FIXED_TIMESTAMP)

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
            _context(actor="phase-i-auto-upgrade"),
        )

    select_events = [
        event
        for event in result.trace.events
        if event.event_kind is AccessTraceKind.SELECT_MODE
    ]
    assert result.resolved_mode is AccessMode.RECALL
    assert [event.mode for event in select_events] == [AccessMode.FLASH, AccessMode.RECALL]
    assert [event.switch_kind for event in select_events] == [
        AccessSwitchKind.INITIAL,
        AccessSwitchKind.UPGRADE,
    ]
    assert select_events[1].reason_code is AccessReasonCode.CONSTRAINT_RISK


def test_auto_downgrades_from_recall_to_flash_when_case_is_simple(tmp_path: Path) -> None:
    with SQLiteMemoryStore(tmp_path / "phase_i_auto_downgrade.sqlite3") as store:
        _seed_store(store)
        service = AccessService(store, clock=lambda: FIXED_TIMESTAMP)

        result = service.run(
            {
                "requested_mode": "auto",
                "task_id": "showcase-task",
                "task_family": "speed_sensitive",
                "time_budget_ms": 500,
                "query": "showcase episode",
                "query_modes": ["keyword"],
                "filters": {"object_types": ["TaskEpisode"], "task_id": "showcase-task"},
            },
            _context(actor="phase-i-auto-downgrade"),
        )

    select_events = [
        event
        for event in result.trace.events
        if event.event_kind is AccessTraceKind.SELECT_MODE
    ]
    assert result.resolved_mode is AccessMode.FLASH
    assert [event.mode for event in select_events] == [AccessMode.RECALL, AccessMode.FLASH]
    assert [event.switch_kind for event in select_events] == [
        AccessSwitchKind.INITIAL,
        AccessSwitchKind.DOWNGRADE,
    ]
    assert select_events[1].reason_code is AccessReasonCode.QUALITY_SATISFIED


def test_auto_jumps_from_reconstruct_to_reflective_on_conflict_signal(tmp_path: Path) -> None:
    with SQLiteMemoryStore(tmp_path / "phase_i_auto_jump.sqlite3") as store:
        _seed_store(store)
        service = AccessService(store, clock=lambda: FIXED_TIMESTAMP)

        result = service.run(
            {
                "requested_mode": "auto",
                "task_id": "task-008",
                "task_family": "high_correctness",
                "query": "Episode 8 stale memory revalidated",
                "query_modes": ["keyword"],
                "filters": {
                    "object_types": ["ReflectionNote", "SummaryNote", "TaskEpisode", "RawRecord"]
                },
            },
            _context(actor="phase-i-auto-jump", budget_limit=100.0),
        )

    select_events = [
        event
        for event in result.trace.events
        if event.event_kind is AccessTraceKind.SELECT_MODE
    ]
    assert result.resolved_mode is AccessMode.REFLECTIVE_ACCESS
    assert [event.mode for event in select_events] == [
        AccessMode.RECONSTRUCT,
        AccessMode.REFLECTIVE_ACCESS,
    ]
    assert [event.switch_kind for event in select_events] == [
        AccessSwitchKind.INITIAL,
        AccessSwitchKind.JUMP,
    ]
    assert select_events[1].reason_code is AccessReasonCode.EVIDENCE_CONFLICT


# --- Phase I independent audit supplementary tests ---


def test_service_rejects_invalid_request_dict(tmp_path: Path) -> None:
    with SQLiteMemoryStore(tmp_path / "phase_i_invalid_req.sqlite3") as store:
        _seed_store(store)
        service = AccessService(store, clock=lambda: FIXED_TIMESTAMP)

        with pytest.raises(AccessServiceError):
            service.run(
                {"requested_mode": "nonexistent_mode", "task_id": "t", "query": "q"},
                _context(),
            )


def test_service_rejects_missing_task_id(tmp_path: Path) -> None:
    with SQLiteMemoryStore(tmp_path / "phase_i_missing_tid.sqlite3") as store:
        _seed_store(store)
        service = AccessService(store, clock=lambda: FIXED_TIMESTAMP)

        with pytest.raises(AccessServiceError):
            service.run(
                {"requested_mode": "flash", "query": "hello"},
                _context(),
            )


def test_auto_balanced_stays_at_recall_without_switch(tmp_path: Path) -> None:
    """Auto mode with balanced family stays at recall when no switch trigger."""
    with SQLiteMemoryStore(tmp_path / "phase_i_auto_no_switch.sqlite3") as store:
        _seed_store(store)
        service = AccessService(store, clock=lambda: FIXED_TIMESTAMP)

        result = service.run(
            {
                "requested_mode": "auto",
                "task_id": "task-001",
                "task_family": "balanced",
                "query": "Episode 1 succeeded with concise replay cues",
                "query_modes": ["keyword"],
                "filters": {"object_types": ["SummaryNote", "TaskEpisode"]},
            },
            _context(actor="phase-i-auto-no-switch"),
        )

    select_events = [
        event
        for event in result.trace.events
        if event.event_kind is AccessTraceKind.SELECT_MODE
    ]
    assert result.resolved_mode is AccessMode.RECALL
    assert len(select_events) == 1, "balanced auto should stay at recall"
    assert select_events[0].switch_kind is AccessSwitchKind.INITIAL
    assert select_events[0].reason_code is AccessReasonCode.BALANCED_DEFAULT


def test_auto_high_correctness_starts_at_reconstruct(tmp_path: Path) -> None:
    """Auto mode with HIGH_CORRECTNESS family selects reconstruct initially."""
    with SQLiteMemoryStore(tmp_path / "phase_i_auto_hc.sqlite3") as store:
        _seed_store(store)
        service = AccessService(store, clock=lambda: FIXED_TIMESTAMP)

        result = service.run(
            {
                "requested_mode": "auto",
                "task_id": "task-001",
                "task_family": "high_correctness",
                "query": "Episode 1 succeeded with concise replay cues",
                "query_modes": ["keyword"],
                "filters": {"object_types": ["SummaryNote", "TaskEpisode"]},
            },
            _context(actor="phase-i-auto-hc"),
        )

    first_select = result.trace.events[0]
    assert first_select.event_kind is AccessTraceKind.SELECT_MODE
    assert first_select.reason_code is AccessReasonCode.HIGH_CORRECTNESS_REQUIRED
    assert result.resolved_mode in {AccessMode.RECONSTRUCT, AccessMode.REFLECTIVE_ACCESS}


def test_flash_trace_has_exactly_four_events(tmp_path: Path) -> None:
    """Flash mode trace: select_mode → retrieve → read → mode_summary."""
    with SQLiteMemoryStore(tmp_path / "phase_i_flash_events.sqlite3") as store:
        _seed_store(store)
        service = AccessService(store, clock=lambda: FIXED_TIMESTAMP)

        result = service.run(
            {
                "requested_mode": "flash",
                "task_id": "task-001",
                "query": "Episode 1 succeeded with concise replay cues",
                "query_modes": ["keyword"],
                "filters": {"object_types": ["SummaryNote"]},
            },
            _context(),
        )

    kinds = [event.event_kind for event in result.trace.events]
    assert kinds == [
        AccessTraceKind.SELECT_MODE,
        AccessTraceKind.RETRIEVE,
        AccessTraceKind.READ,
        AccessTraceKind.MODE_SUMMARY,
    ]
    assert all(event.mode is not AccessMode.AUTO for event in result.trace.events)


def test_all_trace_events_carry_non_auto_mode(tmp_path: Path) -> None:
    """Every event in a trace must use a fixed mode, never AUTO."""
    with SQLiteMemoryStore(tmp_path / "phase_i_trace_modes.sqlite3") as store:
        _seed_store(store)
        service = AccessService(store, clock=lambda: FIXED_TIMESTAMP)

        for mode_value in ("flash", "recall", "reconstruct", "reflective_access", "auto"):
            result = service.run(
                {
                    "requested_mode": mode_value,
                    "task_id": "task-004",
                    "task_family": "high_correctness",
                    "query": "Episode 4 revised corrected replay hints",
                    "query_modes": ["keyword"],
                    "filters": {
                        "object_types": [
                            "ReflectionNote", "SummaryNote", "TaskEpisode", "RawRecord",
                        ]
                    },
                },
                _context(actor=f"phase-i-mode-audit-{mode_value}"),
            )
            for event in result.trace.events:
                assert event.mode is not AccessMode.AUTO, (
                    f"trace event {event.event_kind.value} used AUTO for {mode_value}"
                )


def _seed_store(store: SQLiteMemoryStore) -> None:
    store.insert_objects(build_canonical_seed_objects())
