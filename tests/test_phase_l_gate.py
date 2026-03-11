from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mind.access import AccessService
from mind.fixtures.golden_episode_set import build_golden_episode_set
from mind.fixtures.retrieval_benchmark import build_canonical_seed_objects
from mind.governance import GovernanceService
from mind.kernel.governance import ConcealExecuteRequest, ConcealPreviewRequest
from mind.kernel.store import SQLiteMemoryStore
from mind.offline import (
    OfflineJobKind,
    OfflineMaintenanceService,
    ReflectEpisodeJobPayload,
    new_offline_job,
)
from mind.primitives.contracts import Capability, PrimitiveExecutionContext
from mind.primitives.service import PrimitiveService
from mind.telemetry import (
    InMemoryTelemetryRecorder,
    TelemetryEvent,
    TelemetryEventKind,
    TelemetryScope,
    assert_telemetry_gate,
    evaluate_telemetry_gate,
    evaluate_telemetry_toggle_audit,
    read_telemetry_gate_report_json,
    write_telemetry_gate_report_json,
)

FIXED_TIMESTAMP = datetime(2026, 3, 12, 5, 0, tzinfo=UTC)


def _context(
    *,
    actor: str,
    capabilities: list[Capability],
    dev_mode: bool = False,
    telemetry_run_id: str | None = None,
    budget_limit: float = 100.0,
) -> PrimitiveExecutionContext:
    return PrimitiveExecutionContext(
        actor=actor,
        budget_scope_id=f"phase-l-gate::{actor}",
        budget_limit=budget_limit,
        capabilities=capabilities,
        dev_mode=dev_mode,
        telemetry_run_id=telemetry_run_id,
    )


def test_phase_l_gate_passes_on_recorded_flows(tmp_path: Path) -> None:
    result = _evaluate_passing_gate_result(tmp_path)

    assert result.l1_pass
    assert result.l2_pass
    assert result.l3_pass
    assert result.l4_pass
    assert result.l5_pass
    assert result.l6_pass
    assert result.toggle_audit.disabled_event_count == 0
    assert result.toggle_audit.scenario_count == 2
    assert result.toggle_audit.matching_scenario_count == 2
    assert result.telemetry_gate_pass
    assert_telemetry_gate(result)


def test_phase_l_gate_report_writes_json(tmp_path: Path) -> None:
    result = _evaluate_passing_gate_result(tmp_path)

    output_path = write_telemetry_gate_report_json(
        tmp_path / "phase_l_gate_report.json",
        result,
        generated_at=FIXED_TIMESTAMP,
    )
    payload = read_telemetry_gate_report_json(output_path)

    assert payload["schema_version"] == "telemetry_gate_report_v1"
    assert payload["generated_at"] == FIXED_TIMESTAMP.isoformat()
    assert payload["telemetry_gate_pass"] is True
    assert payload["l4_pass"] is True
    assert payload["toggle_audit"]["disabled_event_count"] == 0
    assert payload["toggle_audit"]["scenario_count"] == 2
    assert len(payload["toggle_audit"]["scenario_results"]) == 2
    assert payload["coverage_audit"]["coverage"] == 1.0


def test_phase_l_gate_fails_on_toggle_drift(tmp_path: Path) -> None:
    events = _record_phase_l_events(tmp_path / "phase_l_gate_fail.sqlite3")
    toggle_result = evaluate_telemetry_toggle_audit(
        disabled_events=(
            TelemetryEvent(
                event_id="toggle-disabled-event",
                scope=TelemetryScope.PRIMITIVE,
                kind=TelemetryEventKind.ENTRY,
                occurred_at=FIXED_TIMESTAMP,
                run_id="run-toggle-fail",
                operation_id="primitive-toggle-fail",
                payload={"primitive": "read"},
            ),
        ),
        comparisons=(
            (
                "access_recall",
                {"resolved_mode": "recall", "selected_count": 2},
                {"resolved_mode": "recall", "selected_count": 1},
            ),
        ),
    )

    result = evaluate_telemetry_gate(events, toggle_audit=toggle_result)

    assert not result.l4_pass
    assert not result.telemetry_gate_pass
    assert result.toggle_audit.disabled_event_count == 1
    assert result.toggle_audit.drift_scenario_ids == ("access_recall",)
    with pytest.raises(RuntimeError, match="L-4 failed"):
        assert_telemetry_gate(result)


def _evaluate_passing_gate_result(tmp_path: Path):
    events = _record_phase_l_events(tmp_path / "phase_l_gate.sqlite3")
    toggle_audit = _evaluate_toggle_audit(tmp_path)
    return evaluate_telemetry_gate(events, toggle_audit=toggle_audit)


def _record_phase_l_events(db_path: Path) -> tuple[TelemetryEvent, ...]:
    recorder = InMemoryTelemetryRecorder()
    offline_episode = build_golden_episode_set()[3]

    with SQLiteMemoryStore(db_path) as store:
        primitive_service = PrimitiveService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )
        primitive_service.write_raw(
            {
                "record_kind": "assistant_message",
                "content": {"text": "gate seed raw object"},
                "episode_id": "episode-gate-seed",
                "timestamp_order": 1,
                "direct_provenance": {
                    "producer_kind": "user",
                    "producer_id": "user-a",
                    "captured_at": "2026-03-09T10:00:00+00:00",
                    "source_channel": "chat",
                    "tenant_id": "tenant-a",
                    "user_id": "user-a",
                    "session_id": "session-a",
                    "episode_id": "episode-gate-seed",
                },
            },
            _context(
                actor="phase-l-gate-writer",
                capabilities=[Capability.MEMORY_READ],
                dev_mode=True,
                telemetry_run_id="run-phase-l-gate-primitive",
            ),
        )
        primitive_service.write_raw(
            {
                "record_kind": "assistant_message",
                "content": {"text": "gate budget rejection"},
                "episode_id": "episode-gate-budget",
                "timestamp_order": 1,
            },
            _context(
                actor="phase-l-gate-writer",
                capabilities=[Capability.MEMORY_READ],
                dev_mode=True,
                telemetry_run_id="run-phase-l-gate-budget",
                budget_limit=0.1,
            ),
        )

        store.insert_objects(build_canonical_seed_objects())
        access_service = AccessService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )
        access_service.run(
            {
                "requested_mode": "recall",
                "task_id": "task-l-gate",
                "query": "Episode 4 revised corrected replay hints",
                "query_modes": ["keyword"],
                "filters": {"object_types": ["SummaryNote", "TaskEpisode"]},
            },
            _context(
                actor="phase-l-gate-access",
                capabilities=[Capability.MEMORY_READ],
                dev_mode=True,
                telemetry_run_id="run-phase-l-gate-access",
            ),
        )

        offline_service = OfflineMaintenanceService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )
        offline_service.process_job(
            new_offline_job(
                job_id="phase-l-gate-offline",
                job_kind=OfflineJobKind.REFLECT_EPISODE,
                payload=ReflectEpisodeJobPayload(
                    episode_id=offline_episode.episode_id,
                    focus="phase l gate audit",
                ),
                now=FIXED_TIMESTAMP,
            ),
            actor="phase-l-gate-offline",
            dev_mode=True,
            telemetry_run_id="run-phase-l-gate-offline",
        )

        governance_service = GovernanceService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )
        plan = governance_service.plan_conceal(
            {
                "selector": {"producer_id": "user-a"},
                "reason": "phase l gate conceal",
            },
            _context(
                actor="phase-l-gate-governance-plan",
                capabilities=[Capability.GOVERNANCE_PLAN],
                dev_mode=True,
                telemetry_run_id="run-phase-l-gate-governance",
            ),
        )
        governance_service.preview_conceal(
            ConcealPreviewRequest(operation_id=plan.operation_id),
            _context(
                actor="phase-l-gate-governance-preview",
                capabilities=[Capability.GOVERNANCE_PLAN],
                dev_mode=True,
                telemetry_run_id="run-phase-l-gate-governance",
            ),
        )
        governance_service.execute_conceal(
            ConcealExecuteRequest(operation_id=plan.operation_id),
            _context(
                actor="phase-l-gate-governance-execute",
                capabilities=[Capability.GOVERNANCE_EXECUTE],
                dev_mode=True,
                telemetry_run_id="run-phase-l-gate-governance",
            ),
        )

    return tuple(recorder.iter_events())


def _evaluate_toggle_audit(tmp_path: Path):
    disabled_recorder = InMemoryTelemetryRecorder()
    enabled_read = _run_read_projection(
        tmp_path / "phase_l_toggle_enabled_read.sqlite3",
        dev_mode=True,
        recorder=InMemoryTelemetryRecorder(),
    )
    disabled_read = _run_read_projection(
        tmp_path / "phase_l_toggle_disabled_read.sqlite3",
        dev_mode=False,
        recorder=disabled_recorder,
    )
    enabled_access = _run_access_projection(
        tmp_path / "phase_l_toggle_enabled_access.sqlite3",
        dev_mode=True,
        recorder=InMemoryTelemetryRecorder(),
    )
    disabled_access = _run_access_projection(
        tmp_path / "phase_l_toggle_disabled_access.sqlite3",
        dev_mode=False,
        recorder=disabled_recorder,
    )
    return evaluate_telemetry_toggle_audit(
        disabled_events=tuple(disabled_recorder.iter_events()),
        comparisons=(
            ("primitive_read", enabled_read, disabled_read),
            ("access_recall", enabled_access, disabled_access),
        ),
    )


def _run_read_projection(
    db_path: Path,
    *,
    dev_mode: bool,
    recorder: InMemoryTelemetryRecorder,
) -> dict[str, object]:
    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(build_canonical_seed_objects())
        primitive_service = PrimitiveService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )
        result = primitive_service.read(
            {"object_ids": ["showcase-summary", "showcase-reflection"]},
            _context(
                actor="phase-l-toggle-read",
                capabilities=[Capability.MEMORY_READ],
                dev_mode=dev_mode,
                telemetry_run_id=f"run-phase-l-toggle-read-{dev_mode}",
            ),
        )

    assert result.response is not None
    return {
        "primitive": result.primitive.value,
        "outcome": result.outcome.value,
        "target_ids": list(result.target_ids),
        "object_ids": [obj["id"] for obj in result.response["objects"]],
        "object_types": [obj["type"] for obj in result.response["objects"]],
        "object_versions": [obj["version"] for obj in result.response["objects"]],
    }


def _run_access_projection(
    db_path: Path,
    *,
    dev_mode: bool,
    recorder: InMemoryTelemetryRecorder,
) -> dict[str, object]:
    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(build_canonical_seed_objects())
        access_service = AccessService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )
        response = access_service.run(
            {
                "requested_mode": "recall",
                "task_id": "task-phase-l-toggle",
                "query": "Episode 4 revised corrected replay hints",
                "query_modes": ["keyword"],
                "filters": {"object_types": ["SummaryNote", "TaskEpisode"]},
            },
            _context(
                actor="phase-l-toggle-access",
                capabilities=[Capability.MEMORY_READ],
                dev_mode=dev_mode,
                telemetry_run_id=f"run-phase-l-toggle-access-{dev_mode}",
            ),
        )

    return {
        "resolved_mode": response.resolved_mode.value,
        "context_kind": response.context_kind.value,
        "candidate_ids": list(response.candidate_ids),
        "selected_object_ids": list(response.selected_object_ids),
        "read_object_ids": list(response.read_object_ids),
        "trace_events": [
            {
                "event_kind": event.event_kind.value,
                "mode": event.mode.value,
                "reason_code": event.reason_code.value if event.reason_code is not None else None,
                "summary": event.summary,
            }
            for event in response.trace.events
        ],
    }
