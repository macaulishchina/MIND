from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

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
    evaluate_telemetry_coverage_audit,
    evaluate_telemetry_debug_field_audit,
    evaluate_telemetry_state_delta_audit,
    evaluate_telemetry_timeline_audit,
    evaluate_telemetry_trace_audit,
)

FIXED_TIMESTAMP = datetime(2026, 3, 12, 3, 30, tzinfo=UTC)


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
        budget_scope_id=f"phase-l::{actor}",
        budget_limit=budget_limit,
        capabilities=capabilities,
        dev_mode=dev_mode,
        telemetry_run_id=telemetry_run_id,
    )


def test_phase_l_telemetry_audits_pass_on_recorded_flows(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()
    offline_episode = build_golden_episode_set()[3]

    with SQLiteMemoryStore(tmp_path / "phase_l_telemetry_audit.sqlite3") as store:
        primitive_service = PrimitiveService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )
        primitive_service.write_raw(
            {
                "record_kind": "assistant_message",
                "content": {"text": "audit seed raw object"},
                "episode_id": "episode-audit-seed",
                "timestamp_order": 1,
                "direct_provenance": {
                    "producer_kind": "user",
                    "producer_id": "user-a",
                    "captured_at": "2026-03-09T10:00:00+00:00",
                    "source_channel": "chat",
                    "tenant_id": "tenant-a",
                    "user_id": "user-a",
                    "session_id": "session-a",
                    "episode_id": "episode-audit-seed",
                },
            },
            _context(
                actor="phase-l-audit-writer",
                capabilities=[Capability.MEMORY_READ],
                dev_mode=True,
                telemetry_run_id="run-phase-l-audit-primitive",
            ),
        )
        primitive_service.write_raw(
            {
                "record_kind": "assistant_message",
                "content": {"text": "budget rejection"},
                "episode_id": "episode-audit-budget",
                "timestamp_order": 1,
            },
            _context(
                actor="phase-l-audit-writer",
                capabilities=[Capability.MEMORY_READ],
                dev_mode=True,
                telemetry_run_id="run-phase-l-audit-primitive-budget",
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
                "task_id": "task-004",
                "query": "Episode 4 revised corrected replay hints",
                "query_modes": ["keyword"],
                "filters": {"object_types": ["SummaryNote", "TaskEpisode"]},
            },
            _context(
                actor="phase-l-audit-access",
                capabilities=[Capability.MEMORY_READ],
                dev_mode=True,
                telemetry_run_id="run-phase-l-audit-access",
            ),
        )

        offline_service = OfflineMaintenanceService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )
        offline_service.process_job(
            new_offline_job(
                job_id="phase-l-audit-offline",
                job_kind=OfflineJobKind.REFLECT_EPISODE,
                payload=ReflectEpisodeJobPayload(
                    episode_id=offline_episode.episode_id,
                    focus="phase l telemetry audit",
                ),
                now=FIXED_TIMESTAMP,
            ),
            actor="phase-l-audit-offline",
            dev_mode=True,
            telemetry_run_id="run-phase-l-audit-offline",
        )

        governance_service = GovernanceService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )
        plan = governance_service.plan_conceal(
            {
                "selector": {"producer_id": "user-a"},
                "reason": "phase l telemetry audit conceal",
            },
            _context(
                actor="phase-l-audit-governance-plan",
                capabilities=[Capability.GOVERNANCE_PLAN],
                dev_mode=True,
                telemetry_run_id="run-phase-l-audit-governance",
            ),
        )
        governance_service.preview_conceal(
            ConcealPreviewRequest(operation_id=plan.operation_id),
            _context(
                actor="phase-l-audit-governance-plan",
                capabilities=[Capability.GOVERNANCE_PLAN],
                dev_mode=True,
                telemetry_run_id="run-phase-l-audit-governance",
            ),
        )
        governance_service.execute_conceal(
            ConcealExecuteRequest(operation_id=plan.operation_id),
            _context(
                actor="phase-l-audit-governance-execute",
                capabilities=[Capability.GOVERNANCE_EXECUTE],
                dev_mode=True,
                telemetry_run_id="run-phase-l-audit-governance",
            ),
        )

    events = tuple(recorder.iter_events())
    coverage_result = evaluate_telemetry_coverage_audit(events)
    debug_field_result = evaluate_telemetry_debug_field_audit(events)
    trace_result = evaluate_telemetry_trace_audit(events)
    state_delta_result = evaluate_telemetry_state_delta_audit(events)
    timeline_result = evaluate_telemetry_timeline_audit(events)

    assert coverage_result.passed
    assert coverage_result.coverage == 1.0
    assert debug_field_result.passed
    assert debug_field_result.coverage == 1.0
    assert debug_field_result.applicable_rule_count >= 5
    assert trace_result.passed
    assert trace_result.coverage == 1.0
    assert trace_result.audited_event_count == len(events)
    assert state_delta_result.passed
    assert state_delta_result.coverage == 1.0
    assert state_delta_result.audited_event_count >= 1
    assert timeline_result.passed
    assert timeline_result.replayable_ratio == 1.0
    assert timeline_result.audited_run_count >= 4


def test_trace_audit_detects_missing_object_version_and_parent_reference() -> None:
    events = (
        TelemetryEvent(
            event_id="delta-001",
            scope=TelemetryScope.OBJECT_DELTA,
            kind=TelemetryEventKind.STATE_DELTA,
            occurred_at=FIXED_TIMESTAMP,
            run_id="run-audit-bad",
            operation_id="op-audit-bad",
            object_id="obj-001",
            before={},
            after={"id": "obj-001", "version": 1},
            delta={"version": {"before": None, "after": 1}},
            payload={"primitive": "write_raw"},
        ),
        TelemetryEvent(
            event_id="child-001",
            scope=TelemetryScope.PRIMITIVE,
            kind=TelemetryEventKind.ACTION_RESULT,
            occurred_at=FIXED_TIMESTAMP,
            run_id="run-audit-bad",
            operation_id="op-audit-bad",
            parent_event_id="missing-parent",
            payload={"primitive": "write_raw", "outcome": "success"},
        ),
    )

    result = evaluate_telemetry_trace_audit(events)

    assert not result.passed
    assert result.missing_object_version_count == 1
    assert result.missing_parent_event_count == 1
    assert result.coverage == 0.0


def test_timeline_audit_detects_out_of_order_parent_event() -> None:
    child = TelemetryEvent(
        event_id="child-002",
        scope=TelemetryScope.PRIMITIVE,
        kind=TelemetryEventKind.ACTION_RESULT,
        occurred_at=FIXED_TIMESTAMP,
        run_id="run-audit-order",
        operation_id="op-audit-order",
        parent_event_id="entry-002",
        payload={"primitive": "write_raw", "outcome": "success"},
    )
    parent = TelemetryEvent(
        event_id="entry-002",
        scope=TelemetryScope.PRIMITIVE,
        kind=TelemetryEventKind.ENTRY,
        occurred_at=FIXED_TIMESTAMP,
        run_id="run-audit-order",
        operation_id="op-audit-order",
        payload={"primitive": "write_raw", "request": {"episode_id": "ep-1"}},
    )

    result = evaluate_telemetry_timeline_audit((child, parent))

    assert not result.passed
    assert result.replayable_ratio == 0.0
    assert result.run_results[0].out_of_order_parent_event_count == 1
    assert result.run_results[0].replayable is False


def test_coverage_audit_detects_missing_scope() -> None:
    events = (
        TelemetryEvent(
            event_id="primitive-entry-only",
            scope=TelemetryScope.PRIMITIVE,
            kind=TelemetryEventKind.ENTRY,
            occurred_at=FIXED_TIMESTAMP,
            run_id="run-coverage-missing",
            operation_id="op-coverage-missing",
            payload={"primitive": "write_raw", "request": {"episode_id": "ep-1"}},
        ),
    )

    result = evaluate_telemetry_coverage_audit(events)

    assert not result.passed
    assert result.coverage == round(1 / 7, 4)
    assert TelemetryScope.RETRIEVAL in result.missing_scopes
    assert TelemetryScope.GOVERNANCE in result.missing_scopes


def test_debug_field_audit_detects_missing_required_fields() -> None:
    events = (
        TelemetryEvent(
            event_id="retrieval-decision-bad",
            scope=TelemetryScope.RETRIEVAL,
            kind=TelemetryEventKind.DECISION,
            occurred_at=FIXED_TIMESTAMP,
            run_id="run-debug-missing",
            operation_id="op-debug-missing",
            payload={
                "retrieval_backend": "store_search",
                "candidate_ids": ["obj-1"],
            },
            debug_fields={},
        ),
        TelemetryEvent(
            event_id="access-decision-good",
            scope=TelemetryScope.ACCESS,
            kind=TelemetryEventKind.DECISION,
            occurred_at=FIXED_TIMESTAMP,
            run_id="run-debug-missing",
            operation_id="op-debug-missing",
            payload={
                "mode": "flash",
                "reason_code": "explicit_mode_request",
                "switch_kind": "initial",
                "target_ids": [],
            },
            debug_fields={"summary": "ok"},
        ),
    )

    result = evaluate_telemetry_debug_field_audit(events)

    assert not result.passed
    assert result.audited_event_count == 2
    retrieval_rule = next(rule for rule in result.rule_results if rule.rule_id == "retrieval_ranking")
    assert retrieval_rule.matched_event_count == 1
    assert retrieval_rule.complete_event_count == 0
    assert retrieval_rule.incomplete_event_ids == ("retrieval-decision-bad",)
