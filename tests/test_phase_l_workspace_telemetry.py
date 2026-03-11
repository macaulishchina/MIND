from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mind.access import AccessService
from mind.fixtures.golden_episode_set import build_core_object_showcase
from mind.fixtures.retrieval_benchmark import build_canonical_seed_objects
from mind.kernel.store import SQLiteMemoryStore
from mind.primitives.contracts import Capability, PrimitiveExecutionContext
from mind.telemetry import InMemoryTelemetryRecorder, TelemetryEventKind, TelemetryScope
from mind.workspace import WorkspaceBuilder

FIXED_TIMESTAMP = datetime(2026, 3, 12, 0, 15, tzinfo=UTC)


def _context(
    *,
    dev_mode: bool = False,
    telemetry_run_id: str | None = None,
) -> PrimitiveExecutionContext:
    return PrimitiveExecutionContext(
        actor="phase-l-workspace",
        budget_scope_id="phase-l-workspace",
        budget_limit=50.0,
        capabilities=[Capability.MEMORY_READ],
        dev_mode=dev_mode,
        telemetry_run_id=telemetry_run_id,
    )


def test_workspace_builder_emits_workspace_events_in_dev_mode(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()
    showcase = build_core_object_showcase()

    with SQLiteMemoryStore(tmp_path / "phase_l_workspace_builder.sqlite3") as store:
        store.insert_objects(showcase)
        builder = WorkspaceBuilder(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )

        result = builder.build(
            task_id="showcase-task",
            candidate_ids=["showcase-summary", "showcase-reflection", "showcase-summary"],
            candidate_scores=[0.9, 0.6, 0.4],
            slot_limit=2,
            dev_mode=True,
            telemetry_run_id="run-phase-l-workspace-001",
        )

    assert result.selected_ids == ("showcase-summary", "showcase-reflection")
    events = tuple(recorder.iter_events())
    assert len(events) == 3
    assert [event.scope for event in events] == [
        TelemetryScope.WORKSPACE,
        TelemetryScope.WORKSPACE,
        TelemetryScope.WORKSPACE,
    ]
    assert [event.kind for event in events] == [
        TelemetryEventKind.ENTRY,
        TelemetryEventKind.DECISION,
        TelemetryEventKind.CONTEXT_RESULT,
    ]
    assert all(event.run_id == "run-phase-l-workspace-001" for event in events)
    assert all(event.workspace_id == "workspace-showcase-task" for event in events)
    assert events[0].debug_fields["candidate_count"] == 3
    assert events[1].payload["selected_ids"] == ["showcase-summary", "showcase-reflection"]
    assert events[1].debug_fields["deduped_candidate_count"] == 2
    assert events[2].payload["workspace_object"]["content"]["selected_object_ids"] == [
        "showcase-summary",
        "showcase-reflection",
    ]


def test_workspace_builder_does_not_emit_when_dev_mode_disabled(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()
    showcase = build_core_object_showcase()

    with SQLiteMemoryStore(tmp_path / "phase_l_workspace_builder_off.sqlite3") as store:
        store.insert_objects(showcase)
        builder = WorkspaceBuilder(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )

        builder.build(
            task_id="showcase-task",
            candidate_ids=["showcase-summary", "showcase-reflection"],
            candidate_scores=[0.9, 0.6],
            slot_limit=2,
        )

    assert tuple(recorder.iter_events()) == ()


def test_access_recall_path_emits_workspace_events(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()

    with SQLiteMemoryStore(tmp_path / "phase_l_access_workspace.sqlite3") as store:
        store.insert_objects(build_canonical_seed_objects())
        service = AccessService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )

        result = service.run(
            {
                "requested_mode": "recall",
                "task_id": "task-004",
                "query": "Episode 4 revised corrected replay hints",
                "query_modes": ["keyword"],
                "filters": {"object_types": ["SummaryNote", "TaskEpisode"]},
            },
            _context(dev_mode=True, telemetry_run_id="run-phase-l-workspace-002"),
        )

    assert result.selected_object_ids
    workspace_events = [
        event for event in recorder.iter_events() if event.scope is TelemetryScope.WORKSPACE
    ]
    assert len(workspace_events) == 3
    assert [event.kind for event in workspace_events] == [
        TelemetryEventKind.ENTRY,
        TelemetryEventKind.DECISION,
        TelemetryEventKind.CONTEXT_RESULT,
    ]
    assert all(event.run_id == "run-phase-l-workspace-002" for event in workspace_events)
    assert workspace_events[0].workspace_id == "workspace-recall-task-004"
    assert workspace_events[0].parent_event_id == "access-task-004-entry"
    assert workspace_events[1].payload["selected_ids"] == result.selected_object_ids
    assert (
        workspace_events[2].payload["workspace_object"]["content"]["selected_object_ids"]
        == result.selected_object_ids
    )
