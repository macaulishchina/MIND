from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mind.fixtures.golden_episode_set import build_core_object_showcase, build_golden_episode_set
from mind.kernel.schema import validate_object
from mind.kernel.store import SQLiteMemoryStore
from mind.workspace import WorkspaceBuilder

FIXED_TIMESTAMP = datetime(2026, 3, 9, 16, 0, tzinfo=UTC)


def test_workspace_builder_creates_valid_workspace_view(tmp_path: Path) -> None:
    db_path = tmp_path / "workspace_builder.sqlite3"
    showcase = build_core_object_showcase()
    episode = build_golden_episode_set()[3]

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(showcase)
        store.insert_objects(episode.objects)
        builder = WorkspaceBuilder(store, clock=lambda: FIXED_TIMESTAMP)

        result = builder.build(
            task_id=episode.task_id,
            candidate_ids=[
                f"{episode.episode_id}-summary",
                showcase[2]["id"],
                showcase[3]["id"],
                episode.episode_id,
                f"{episode.episode_id}-summary",
            ],
            candidate_scores=[0.9, 0.7, 0.6, 0.5, 0.4],
            slot_limit=3,
        )

    workspace = result.workspace
    assert validate_object(workspace) == []
    assert workspace["type"] == "WorkspaceView"
    assert workspace["metadata"]["task_id"] == episode.task_id
    assert workspace["metadata"]["slot_limit"] == 3
    assert len(workspace["metadata"]["slots"]) == 3
    assert result.selected_ids == (
        f"{episode.episode_id}-summary",
        "showcase-summary",
        "showcase-reflection",
    )
    assert result.skipped_ids == ()
    assert all(slot["source_refs"] for slot in workspace["metadata"]["slots"])
    assert all(slot["evidence_refs"] for slot in workspace["metadata"]["slots"])


def test_workspace_builder_skips_invalid_candidates(tmp_path: Path) -> None:
    db_path = tmp_path / "workspace_builder_invalid.sqlite3"
    showcase = build_core_object_showcase()
    invalid_workspace: dict[str, Any] = {
        "id": "invalid-workspace",
        "type": "WorkspaceView",
        "content": {"purpose": "invalid workspace"},
        "source_refs": [showcase[2]["id"]],
        "created_at": FIXED_TIMESTAMP.isoformat(),
        "updated_at": FIXED_TIMESTAMP.isoformat(),
        "version": 1,
        "status": "invalid",
        "priority": 0.4,
        "metadata": {
            "task_id": "showcase-task",
            "slot_limit": 1,
            "slots": [
                {
                    "slot_id": "slot-1",
                    "summary": "ignore me",
                    "evidence_refs": [showcase[0]["id"]],
                    "source_refs": [showcase[2]["id"]],
                    "reason_selected": "invalid",
                    "priority": 0.4,
                    "expand_pointer": {"object_id": showcase[2]["id"]},
                }
            ],
            "selection_policy": "priority-first",
        },
    }

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(showcase)
        store.insert_object(invalid_workspace)
        builder = WorkspaceBuilder(store, clock=lambda: FIXED_TIMESTAMP)

        result = builder.build(
            task_id="showcase-task",
            candidate_ids=[invalid_workspace["id"], showcase[2]["id"]],
            candidate_scores=[0.9, 0.5],
            slot_limit=2,
        )

    assert result.selected_ids == ("showcase-summary",)
    assert result.skipped_ids == ("invalid-workspace",)
    assert len(result.workspace["metadata"]["slots"]) == 1
