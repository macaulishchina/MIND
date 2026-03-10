from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mind.fixtures.golden_episode_set import build_core_object_showcase
from mind.kernel.governance import ConcealmentRecord
from mind.kernel.store import SQLiteMemoryStore
from mind.primitives.contracts import PrimitiveExecutionContext, PrimitiveOutcome
from mind.primitives.service import PrimitiveService
from mind.workspace import WorkspaceBuilder

FIXED_TIMESTAMP = datetime(2026, 3, 10, 11, 0, tzinfo=UTC)


def _context() -> PrimitiveExecutionContext:
    return PrimitiveExecutionContext(
        actor="phase-h-conceal-test",
        budget_scope_id="phase-h-conceal",
        budget_limit=20.0,
    )


def test_online_paths_hide_concealed_objects(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_h_conceal_online.sqlite3"
    showcase = build_core_object_showcase()
    concealed_id = "showcase-summary"
    visible_id = "showcase-reflection"

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(showcase)
        store.record_concealment(
            ConcealmentRecord(
                concealment_id="conceal-001",
                operation_id="op-conceal-001",
                object_id=concealed_id,
                actor="governance-operator",
                concealed_at=FIXED_TIMESTAMP,
                reason="targeted conceal for online isolation",
            )
        )

        service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)
        builder = WorkspaceBuilder(store, clock=lambda: FIXED_TIMESTAMP)

        assert store.is_object_concealed(concealed_id)
        assert store.concealment_for_object(concealed_id).reason == (
            "targeted conceal for online isolation"
        )

        read_result = service.read({"object_ids": [concealed_id]}, _context())
        retrieve_result = service.retrieve(
            {
                "query": "showcase summary",
                "query_modes": ["keyword"],
                "budget": {"max_cost": 5.0, "max_candidates": 5},
                "filters": {"object_types": ["SummaryNote"]},
            },
            _context(),
        )
        workspace_result = builder.build(
            task_id="showcase-task",
            candidate_ids=[concealed_id, visible_id],
            candidate_scores=[0.9, 0.5],
            slot_limit=2,
        )

    assert read_result.outcome is PrimitiveOutcome.REJECTED
    assert read_result.error is not None
    assert read_result.error.code.value == "object_inaccessible"
    assert retrieve_result.outcome is PrimitiveOutcome.SUCCESS
    assert retrieve_result.response is not None
    assert concealed_id not in retrieve_result.response["candidate_ids"]
    assert workspace_result.selected_ids == (visible_id,)
    assert workspace_result.skipped_ids == (concealed_id,)
