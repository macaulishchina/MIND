from __future__ import annotations

from datetime import UTC, datetime

import pytest

from mind.telemetry import (
    TELEMETRY_COVERAGE_SURFACES,
    TelemetryEvent,
    TelemetryEventKind,
    TelemetryScope,
)


def _timestamp() -> datetime:
    return datetime(2026, 3, 11, 23, 0, tzinfo=UTC)


def test_telemetry_coverage_surfaces_are_frozen() -> None:
    assert TELEMETRY_COVERAGE_SURFACES == (
        TelemetryScope.PRIMITIVE,
        TelemetryScope.RETRIEVAL,
        TelemetryScope.WORKSPACE,
        TelemetryScope.ACCESS,
        TelemetryScope.OFFLINE,
        TelemetryScope.GOVERNANCE,
        TelemetryScope.OBJECT_DELTA,
    )


def test_state_delta_event_requires_before_after_delta_and_object_id() -> None:
    event = TelemetryEvent(
        event_id="evt-001",
        scope=TelemetryScope.OBJECT_DELTA,
        kind=TelemetryEventKind.STATE_DELTA,
        occurred_at=_timestamp(),
        run_id="run-001",
        operation_id="op-001",
        object_id="obj-001",
        before={"status": "active"},
        after={"status": "archived"},
        delta={"status": ["active", "archived"]},
    )

    assert event.object_id == "obj-001"
    assert event.delta == {"status": ["active", "archived"]}


def test_partial_delta_shape_is_rejected() -> None:
    with pytest.raises(ValueError, match="before/after/delta must be provided together"):
        TelemetryEvent(
            event_id="evt-002",
            scope=TelemetryScope.OBJECT_DELTA,
            kind=TelemetryEventKind.STATE_DELTA,
            occurred_at=_timestamp(),
            run_id="run-001",
            operation_id="op-001",
            object_id="obj-001",
            before={"status": "active"},
            after={"status": "archived"},
        )


def test_workspace_events_require_workspace_id() -> None:
    with pytest.raises(ValueError, match="workspace events require workspace_id"):
        TelemetryEvent(
            event_id="evt-003",
            scope=TelemetryScope.WORKSPACE,
            kind=TelemetryEventKind.CONTEXT_RESULT,
            occurred_at=_timestamp(),
            run_id="run-001",
            operation_id="op-001",
        )


def test_offline_events_require_job_id() -> None:
    with pytest.raises(ValueError, match="offline/governance events require job_id"):
        TelemetryEvent(
            event_id="evt-004",
            scope=TelemetryScope.OFFLINE,
            kind=TelemetryEventKind.ENTRY,
            occurred_at=_timestamp(),
            run_id="run-001",
            operation_id="op-001",
        )
