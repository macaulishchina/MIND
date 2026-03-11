from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mind.telemetry import (
    CompositeTelemetryRecorder,
    InMemoryTelemetryRecorder,
    JsonlTelemetryRecorder,
    TelemetryEvent,
    TelemetryEventKind,
    TelemetryScope,
    build_dev_telemetry_recorder,
    resolve_dev_telemetry_path,
)

FIXED_TIMESTAMP = datetime(2026, 3, 12, 7, 0, tzinfo=UTC)


def test_jsonl_recorder_persists_and_round_trips_events(tmp_path: Path) -> None:
    path = tmp_path / "telemetry" / "events.jsonl"
    recorder = JsonlTelemetryRecorder(path)

    recorder.record(
        TelemetryEvent(
            event_id="primitive-entry-001",
            scope=TelemetryScope.PRIMITIVE,
            kind=TelemetryEventKind.ENTRY,
            occurred_at=FIXED_TIMESTAMP,
            run_id="run-001",
            operation_id="op-001",
            payload={"primitive": "write_raw"},
        )
    )
    recorder.record(
        TelemetryEvent(
            event_id="primitive-result-001",
            scope=TelemetryScope.PRIMITIVE,
            kind=TelemetryEventKind.ACTION_RESULT,
            occurred_at=FIXED_TIMESTAMP,
            run_id="run-001",
            operation_id="op-001",
            parent_event_id="primitive-entry-001",
            payload={"primitive": "write_raw", "outcome": "success"},
        )
    )

    assert path.exists()
    events = recorder.iter_events()
    assert [event.event_id for event in events] == [
        "primitive-entry-001",
        "primitive-result-001",
    ]


def test_composite_recorder_fans_out_to_all_sinks(tmp_path: Path) -> None:
    in_memory = InMemoryTelemetryRecorder()
    jsonl = JsonlTelemetryRecorder(tmp_path / "telemetry.jsonl")
    recorder = CompositeTelemetryRecorder((in_memory, jsonl))

    recorder.record(
        TelemetryEvent(
            event_id="workspace-entry-001",
            scope=TelemetryScope.WORKSPACE,
            kind=TelemetryEventKind.ENTRY,
            occurred_at=FIXED_TIMESTAMP,
            run_id="run-002",
            operation_id="workspace-001",
            workspace_id="workspace-001",
            payload={"candidate_count": 3},
        )
    )

    assert len(in_memory.iter_events()) == 1
    assert len(jsonl.iter_events()) == 1


def test_dev_telemetry_path_resolution_prefers_explicit_override(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit.jsonl"
    env = {"MIND_DEV_TELEMETRY_PATH": str(tmp_path / "env.jsonl")}

    resolved = resolve_dev_telemetry_path(telemetry_path=explicit, env=env)
    recorder = build_dev_telemetry_recorder(telemetry_path=explicit, env=env)

    assert resolved == explicit
    assert recorder is not None
    assert recorder.path == explicit


def test_dev_telemetry_path_resolution_uses_env_when_present(tmp_path: Path) -> None:
    env_path = tmp_path / "env-only.jsonl"

    resolved = resolve_dev_telemetry_path(env={"MIND_DEV_TELEMETRY_PATH": str(env_path)})
    recorder = build_dev_telemetry_recorder(env={"MIND_DEV_TELEMETRY_PATH": str(env_path)})

    assert resolved == env_path
    assert recorder is not None
    assert recorder.path == env_path
