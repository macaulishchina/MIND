from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mind.frontend import (
    FrontendDebugTimelineQuery,
    FrontendDebugUnavailableError,
    build_frontend_debug_timeline,
)
from mind.kernel.store import SQLiteMemoryStore
from mind.primitives.contracts import Capability, PrimitiveExecutionContext
from mind.primitives.service import PrimitiveService
from mind.telemetry import (
    InMemoryTelemetryRecorder,
    TelemetryEvent,
    TelemetryEventKind,
    TelemetryScope,
)

FIXED_TIMESTAMP = datetime(2026, 3, 12, 8, 0, tzinfo=UTC)


def _context(*, dev_mode: bool, run_id: str) -> PrimitiveExecutionContext:
    return PrimitiveExecutionContext(
        actor="phase-m-frontend",
        budget_scope_id="phase-m-frontend",
        capabilities=[Capability.MEMORY_READ],
        dev_mode=dev_mode,
        telemetry_run_id=run_id,
    )


def test_frontend_debug_query_requires_filter() -> None:
    with pytest.raises(ValueError, match="at least one filter"):
        FrontendDebugTimelineQuery()


def test_frontend_debug_timeline_rejects_when_dev_mode_is_disabled() -> None:
    with pytest.raises(FrontendDebugUnavailableError, match="dev_mode=true"):
        build_frontend_debug_timeline(
            (),
            {"run_id": "run-disabled"},
            dev_mode=False,
        )


def test_frontend_debug_timeline_projects_manual_events() -> None:
    events = (
        TelemetryEvent(
            event_id="access-entry-001",
            scope=TelemetryScope.ACCESS,
            kind=TelemetryEventKind.ENTRY,
            occurred_at=FIXED_TIMESTAMP,
            run_id="run-frontend-001",
            operation_id="access-op-001",
            payload={"task_id": "task-1", "requested_mode": "recall"},
        ),
        TelemetryEvent(
            event_id="access-decision-001",
            scope=TelemetryScope.ACCESS,
            kind=TelemetryEventKind.DECISION,
            occurred_at=FIXED_TIMESTAMP,
            run_id="run-frontend-001",
            operation_id="access-op-001",
            parent_event_id="access-entry-001",
            payload={"mode": "focus", "reason_code": "balanced_default"},
            debug_fields={"summary": "focus via balanced default"},
        ),
        TelemetryEvent(
            event_id="delta-001",
            scope=TelemetryScope.OBJECT_DELTA,
            kind=TelemetryEventKind.STATE_DELTA,
            occurred_at=FIXED_TIMESTAMP,
            run_id="run-frontend-001",
            operation_id="access-op-001",
            parent_event_id="access-decision-001",
            object_id="obj-001",
            object_version=2,
            before={"status": "draft"},
            after={"status": "active"},
            delta={"status": {"before": "draft", "after": "active"}},
            payload={"primitive": "write_raw"},
        ),
    )

    response = build_frontend_debug_timeline(
        events,
        {
            "run_id": "run-frontend-001",
            "include_payload": True,
            "include_debug_fields": True,
        },
        dev_mode=True,
    )

    assert response.total_event_count == 3
    assert response.matched_event_count == 3
    assert response.returned_event_count == 3
    assert [item.event_id for item in response.timeline] == [
        "access-entry-001",
        "access-decision-001",
        "delta-001",
    ]
    assert response.timeline[1].summary == "focus via balanced_default"
    assert response.timeline[1].debug_fields == {"summary": "focus via balanced default"}
    assert response.timeline[2].label == "Object Delta"
    assert len(response.object_deltas) == 1
    assert response.object_deltas[0].summary == "obj-001 -> v2"


def test_frontend_debug_timeline_filters_by_scope_and_limit() -> None:
    events = (
        TelemetryEvent(
            event_id="primitive-001",
            scope=TelemetryScope.PRIMITIVE,
            kind=TelemetryEventKind.ENTRY,
            occurred_at=FIXED_TIMESTAMP,
            run_id="run-limit-001",
            operation_id="op-limit-001",
            payload={"primitive": "write_raw"},
        ),
        TelemetryEvent(
            event_id="workspace-001",
            scope=TelemetryScope.WORKSPACE,
            kind=TelemetryEventKind.DECISION,
            occurred_at=FIXED_TIMESTAMP,
            run_id="run-limit-001",
            operation_id="op-limit-001",
            workspace_id="workspace-001",
            payload={"selected_ids": ["a", "b"]},
        ),
        TelemetryEvent(
            event_id="workspace-002",
            scope=TelemetryScope.WORKSPACE,
            kind=TelemetryEventKind.CONTEXT_RESULT,
            occurred_at=FIXED_TIMESTAMP,
            run_id="run-limit-001",
            operation_id="op-limit-001",
            workspace_id="workspace-001",
            payload={"selected_ids": ["a", "b"]},
        ),
    )

    response = build_frontend_debug_timeline(
        events,
        {
            "run_id": "run-limit-001",
            "scopes": ["workspace"],
            "limit": 1,
        },
        dev_mode=True,
    )

    assert response.total_event_count == 3
    assert response.matched_event_count == 2
    assert response.returned_event_count == 1
    assert response.timeline[0].scope is TelemetryScope.WORKSPACE
    assert response.available_scopes == [TelemetryScope.WORKSPACE]


def test_frontend_debug_timeline_projects_real_primitive_flow(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()

    with SQLiteMemoryStore(tmp_path / "phase_m_frontend_debug.sqlite3") as store:
        service = PrimitiveService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )
        result = service.write_raw(
            {
                "record_kind": "assistant_message",
                "content": {"text": "frontend projection seed"},
                "episode_id": "phase-m-001",
                "timestamp_order": 1,
            },
            _context(dev_mode=True, run_id="run-phase-m-001"),
        )

    assert result.response is not None
    object_id = str(result.response["object_id"])
    response = build_frontend_debug_timeline(
        tuple(recorder.iter_events()),
        {
            "run_id": "run-phase-m-001",
            "include_state_deltas": True,
        },
        dev_mode=True,
    )

    assert response.returned_event_count >= 3
    assert any(item.scope is TelemetryScope.PRIMITIVE for item in response.timeline)
    assert any(delta.object_id == object_id for delta in response.object_deltas)


def test_frontend_debug_timeline_projects_context_and_evidence_views() -> None:
    events = (
        TelemetryEvent(
            event_id="retrieve-result-001",
            scope=TelemetryScope.RETRIEVAL,
            kind=TelemetryEventKind.ACTION_RESULT,
            occurred_at=FIXED_TIMESTAMP,
            run_id="run-debug-context-001",
            operation_id="access-task-001",
            payload={
                "candidate_summaries": [
                    {
                        "object_id": "obj-001",
                        "object_type": "RawRecord",
                        "content_preview": "remember me",
                        "score": 0.91,
                    },
                    {
                        "object_id": "obj-002",
                        "object_type": "SummaryNote",
                        "content_preview": "summary note",
                        "score": 0.55,
                    },
                ]
            },
        ),
        TelemetryEvent(
            event_id="access-context-001",
            scope=TelemetryScope.ACCESS,
            kind=TelemetryEventKind.CONTEXT_RESULT,
            occurred_at=FIXED_TIMESTAMP,
            run_id="run-debug-context-001",
            operation_id="access-task-001",
            workspace_id="workspace-task-001",
            payload={
                "context_kind": "workspace",
                "context_object_ids": ["workspace-task-001"],
                "candidate_ids": ["obj-001", "obj-002"],
                "selected_object_ids": ["obj-001"],
                "verification_notes": ["support chains traced to source refs"],
            },
        ),
        TelemetryEvent(
            event_id="workspace-result-001",
            scope=TelemetryScope.WORKSPACE,
            kind=TelemetryEventKind.CONTEXT_RESULT,
            occurred_at=FIXED_TIMESTAMP,
            run_id="run-debug-context-001",
            operation_id="access-task-001",
            workspace_id="workspace-task-001",
            payload={
                "workspace_object": {
                    "id": "workspace-task-001",
                    "content": {"selected_object_ids": ["obj-001"]},
                    "metadata": {
                        "slots": [
                            {
                                "slot_id": "slot-1",
                                "summary": "remember me",
                                "evidence_refs": ["raw-ep-1"],
                                "source_refs": ["obj-001"],
                                "reason_selected": "retrieval_score=0.9100",
                                "priority": 0.91,
                                "expand_pointer": {"object_id": "obj-001"},
                            }
                        ]
                    },
                }
            },
        ),
    )

    response = build_frontend_debug_timeline(
        events,
        {"run_id": "run-debug-context-001"},
        dev_mode=True,
    )

    assert len(response.context_views) == 1
    assert response.context_views[0].context_kind == "workspace"
    assert response.context_views[0].selected_object_ids == ["obj-001"]
    assert len(response.evidence_views) == 3
    retrieval_evidence = next(
        view
        for view in response.evidence_views
        if view.event_id == "retrieve-result-001" and view.object_id == "obj-001"
    )
    workspace_evidence = next(
        view for view in response.evidence_views if view.event_id == "workspace-result-001"
    )
    assert retrieval_evidence.selected is True
    assert retrieval_evidence.score == 0.91
    assert workspace_evidence.evidence_refs == ["raw-ep-1"]
    assert workspace_evidence.reason_selected == "retrieval_score=0.9100"


def test_frontend_debug_timeline_surfaces_access_answer_result_summary() -> None:
    events = (
        TelemetryEvent(
            event_id="access-result-001",
            scope=TelemetryScope.ACCESS,
            kind=TelemetryEventKind.ACTION_RESULT,
            occurred_at=FIXED_TIMESTAMP,
            run_id="run-debug-answer-001",
            operation_id="access-task-answer",
            payload={
                "resolved_mode": "recall",
                "answer_text": "episode four required a corrected replay hint",
                "answer_support_ids": ["obj-001"],
                "answer_trace": {
                    "provider_family": "deterministic",
                    "model": "deterministic",
                },
                "summary": "recall answer: episode four required a corrected replay hint",
            },
            debug_fields={"answer_length": 43},
        ),
    )

    response = build_frontend_debug_timeline(
        events,
        {"run_id": "run-debug-answer-001", "include_payload": True, "include_debug_fields": True},
        dev_mode=True,
    )

    assert response.returned_event_count == 1
    assert response.timeline[0].summary == "recall answer: episode four required a corrected replay hint"
    assert response.timeline[0].payload["answer_text"] == (
        "episode four required a corrected replay hint"
    )
    assert response.timeline[0].debug_fields["answer_length"] == 43
