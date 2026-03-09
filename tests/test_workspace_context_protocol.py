from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mind.fixtures.golden_episode_set import build_core_object_showcase, build_golden_episode_set
from mind.kernel.store import SQLiteMemoryStore
from mind.workspace import WorkspaceBuilder
from mind.workspace.context_protocol import (
    PHASE_D_CONTEXT_PROTOCOL,
    build_raw_topk_context,
    build_workspace_context,
)

FIXED_TIMESTAMP = datetime(2026, 3, 9, 16, 0, tzinfo=UTC)


def test_raw_topk_context_is_deterministic(tmp_path: Path) -> None:
    db_path = tmp_path / "workspace_context.sqlite3"
    showcase = build_core_object_showcase()
    episode = build_golden_episode_set()[0]

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(showcase)
        store.insert_objects(episode.objects)

        object_ids = ("showcase-summary", episode.episode_id, f"{episode.episode_id}-summary")
        first = build_raw_topk_context(store, object_ids)
        second = build_raw_topk_context(store, object_ids)

    assert first.protocol == PHASE_D_CONTEXT_PROTOCOL
    assert first.kind == "raw_topk"
    assert first.object_ids == object_ids
    assert first.text == second.text
    assert first.token_count == second.token_count


def test_workspace_context_is_more_compact_than_raw_topk(tmp_path: Path) -> None:
    db_path = tmp_path / "workspace_context_compact.sqlite3"
    showcase = build_core_object_showcase()
    episode = build_golden_episode_set()[3]

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(showcase)
        store.insert_objects(episode.objects)
        builder = WorkspaceBuilder(store, clock=lambda: FIXED_TIMESTAMP)
        workspace_result = builder.build(
            task_id=episode.task_id,
            candidate_ids=[
                f"{episode.episode_id}-summary",
                episode.episode_id,
                showcase[2]["id"],
            ],
            candidate_scores=[0.9, 0.7, 0.6],
            slot_limit=2,
        )
        workspace_context = build_workspace_context(workspace_result.workspace)
        raw_context = build_raw_topk_context(
            store,
            (
                f"{episode.episode_id}-summary",
                episode.episode_id,
                showcase[2]["id"],
            ),
        )

    assert workspace_context.protocol == PHASE_D_CONTEXT_PROTOCOL
    assert workspace_context.kind == "workspace"
    assert workspace_context.object_ids == workspace_result.selected_ids
    assert workspace_context.token_count < raw_context.token_count
