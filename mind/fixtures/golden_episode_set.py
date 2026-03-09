"""GoldenEpisodeSet v1 for Phase B."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from mind.kernel.replay import episode_record_hash


@dataclass(frozen=True)
class EpisodeFixture:
    episode_id: str
    task_id: str
    objects: list[dict]
    expected_event_hash: str


def build_golden_episode_set() -> list[EpisodeFixture]:
    fixtures: list[EpisodeFixture] = []
    base_time = datetime(2026, 1, 1, tzinfo=UTC)

    for index in range(1, 21):
        episode_id = f"episode-{index:03d}"
        task_id = f"task-{index:03d}"
        has_tool = index % 2 == 0
        has_retry = index % 5 == 0
        success = index % 4 != 0

        clock = base_time + timedelta(hours=index)
        timestamp_order = 1
        raw_records: list[dict] = []

        def next_timestamp() -> str:
            nonlocal clock
            value = clock.isoformat()
            clock += timedelta(minutes=1)
            return value

        def raw_record(
            record_index: int,
            record_kind: str,
            content: dict,
            episode_identifier: str = episode_id,
        ) -> dict:
            created_at = next_timestamp()
            return {
                "id": f"{episode_identifier}-raw-{record_index:02d}",
                "type": "RawRecord",
                "content": content,
                "source_refs": [],
                "created_at": created_at,
                "updated_at": created_at,
                "version": 1,
                "status": "active",
                "priority": 0.4,
                "metadata": {
                    "record_kind": record_kind,
                    "episode_id": episode_identifier,
                    "timestamp_order": record_index,
                },
            }

        raw_records.append(
            raw_record(
                timestamp_order,
                "user_message",
                {"text": f"Please solve task {index} with the stored procedure."},
            )
        )
        timestamp_order += 1

        raw_records.append(
            raw_record(
                timestamp_order,
                "assistant_message",
                {"text": f"Planning episode {index} with available memory."},
            )
        )
        timestamp_order += 1

        if has_tool:
            raw_records.append(
                raw_record(
                    timestamp_order,
                    "tool_call",
                    {"tool": "calendar.lookup", "args": {"task_id": task_id}},
                )
            )
            timestamp_order += 1
            raw_records.append(
                raw_record(
                    timestamp_order,
                    "tool_result",
                    {"result": f"lookup-result-{index}", "ok": True},
                )
            )
            timestamp_order += 1

        if has_retry:
            raw_records.append(
                raw_record(
                    timestamp_order,
                    "system_event",
                    {"event": "retry-triggered", "reason": "transient tool mismatch"},
                )
            )
            timestamp_order += 1
            raw_records.append(
                raw_record(
                    timestamp_order,
                    "tool_call",
                    {"tool": "calendar.lookup", "args": {"task_id": task_id, "retry": True}},
                )
            )
            timestamp_order += 1
            raw_records.append(
                raw_record(
                    timestamp_order,
                    "tool_result",
                    {"result": f"lookup-result-{index}-retry", "ok": True},
                )
            )
            timestamp_order += 1

        raw_records.append(
            raw_record(
                timestamp_order,
                "assistant_message",
                {
                    "text": (
                        f"Task {index} completed successfully."
                        if success
                        else f"Task {index} failed because the remembered data was stale."
                    )
                },
            )
        )

        raw_ids = [record["id"] for record in raw_records]
        task_created_at = next_timestamp()
        task_episode = {
            "id": episode_id,
            "type": "TaskEpisode",
            "content": {
                "title": f"Task Episode {index}",
                "result_summary": "success" if success else "failure",
            },
            "source_refs": raw_ids,
            "created_at": task_created_at,
            "updated_at": task_created_at,
            "version": 1,
            "status": "active",
            "priority": 0.6,
            "metadata": {
                "task_id": task_id,
                "goal": f"Complete task {index}",
                "result": "success" if success else "failure",
                "success": success,
                "record_refs": raw_ids,
            },
        }

        summary_id = f"{episode_id}-summary"
        summary_v1_created_at = next_timestamp()
        summary_v1 = {
            "id": summary_id,
            "type": "SummaryNote",
            "content": {
                "summary": (
                    f"Episode {index} {'succeeded' if success else 'failed'} "
                    "with concise replay cues."
                )
            },
            "source_refs": raw_ids,
            "created_at": summary_v1_created_at,
            "updated_at": summary_v1_created_at,
            "version": 1,
            "status": "active",
            "priority": 0.7 if success else 0.5,
            "metadata": {
                "summary_scope": "episode",
                "input_refs": raw_ids,
                "compression_ratio_estimate": 0.35,
            },
        }

        objects = list(raw_records)
        objects.append(task_episode)
        objects.append(summary_v1)

        if index % 4 == 0:
            summary_v2_created_at = next_timestamp()
            objects.append(
                {
                    "id": summary_id,
                    "type": "SummaryNote",
                    "content": {
                        "summary": f"Episode {index} revised summary with corrected replay hints."
                    },
                    "source_refs": raw_ids,
                    "created_at": summary_v1_created_at,
                    "updated_at": summary_v2_created_at,
                    "version": 2,
                    "status": "active",
                    "priority": 0.72 if success else 0.55,
                    "metadata": {
                        "summary_scope": "episode",
                        "input_refs": raw_ids,
                        "compression_ratio_estimate": 0.32,
                    },
                }
            )

        if not success:
            reflection_created_at = next_timestamp()
            objects.append(
                {
                    "id": f"{episode_id}-reflection",
                    "type": "ReflectionNote",
                    "content": {
                        "summary": (
                            f"Episode {index} exposed stale memory and should be revalidated."
                        )
                    },
                    "source_refs": [task_episode["id"]] + raw_ids[-2:],
                    "created_at": reflection_created_at,
                    "updated_at": reflection_created_at,
                    "version": 1,
                    "status": "active",
                    "priority": 0.8,
                    "metadata": {
                        "episode_id": episode_id,
                        "reflection_kind": "failure",
                        "claims": [
                            "stale-memory",
                            "should-refresh-summary",
                        ],
                    },
                }
            )

        fixtures.append(
            EpisodeFixture(
                episode_id=episode_id,
                task_id=task_id,
                objects=objects,
                expected_event_hash=episode_record_hash(raw_records),
            )
        )

    return fixtures


def build_core_object_showcase() -> list[dict]:
    """Return valid example objects for every core type."""

    created_at = "2026-01-01T00:00:00+00:00"
    updated_at = "2026-01-01T00:01:00+00:00"
    raw = {
        "id": "showcase-raw",
        "type": "RawRecord",
        "content": {"text": "showcase raw record"},
        "source_refs": [],
        "created_at": created_at,
        "updated_at": created_at,
        "version": 1,
        "status": "active",
        "priority": 0.3,
        "metadata": {
            "record_kind": "user_message",
            "episode_id": "showcase-episode",
            "timestamp_order": 1,
        },
    }
    episode = {
        "id": "showcase-episode",
        "type": "TaskEpisode",
        "content": {"title": "showcase episode"},
        "source_refs": [raw["id"]],
        "created_at": updated_at,
        "updated_at": updated_at,
        "version": 1,
        "status": "active",
        "priority": 0.4,
        "metadata": {
            "task_id": "showcase-task",
            "goal": "show all core types",
            "result": "success",
            "success": True,
            "record_refs": [raw["id"]],
        },
    }
    summary = {
        "id": "showcase-summary",
        "type": "SummaryNote",
        "content": {"summary": "showcase summary"},
        "source_refs": [raw["id"]],
        "created_at": updated_at,
        "updated_at": updated_at,
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": {
            "summary_scope": "episode",
            "input_refs": [raw["id"]],
            "compression_ratio_estimate": 0.5,
        },
    }
    reflection = {
        "id": "showcase-reflection",
        "type": "ReflectionNote",
        "content": {"summary": "showcase reflection"},
        "source_refs": [episode["id"], raw["id"]],
        "created_at": updated_at,
        "updated_at": updated_at,
        "version": 1,
        "status": "active",
        "priority": 0.6,
        "metadata": {
            "episode_id": episode["id"],
            "reflection_kind": "success",
            "claims": ["clear-structure"],
        },
    }
    entity = {
        "id": "showcase-entity",
        "type": "EntityNode",
        "content": {"description": "showcase entity"},
        "source_refs": [raw["id"]],
        "created_at": updated_at,
        "updated_at": updated_at,
        "version": 1,
        "status": "active",
        "priority": 0.4,
        "metadata": {
            "entity_name": "calendar.lookup",
            "entity_kind": "tool",
            "alias": ["lookup"],
        },
    }
    link = {
        "id": "showcase-link",
        "type": "LinkEdge",
        "content": {
            "src_id": entity["id"],
            "dst_id": summary["id"],
            "relation_type": "supports",
        },
        "source_refs": [raw["id"]],
        "created_at": updated_at,
        "updated_at": updated_at,
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": {
            "confidence": 0.9,
            "evidence_refs": [raw["id"]],
        },
    }
    workspace = {
        "id": "showcase-workspace",
        "type": "WorkspaceView",
        "content": {"purpose": "showcase workspace"},
        "source_refs": [summary["id"], raw["id"]],
        "created_at": updated_at,
        "updated_at": updated_at,
        "version": 1,
        "status": "active",
        "priority": 0.6,
        "metadata": {
            "task_id": "showcase-task",
            "slot_limit": 4,
            "slots": [
                {
                    "slot_id": "slot-1",
                    "summary": "Use the episode summary first",
                    "evidence_refs": [raw["id"]],
                    "source_refs": [summary["id"]],
                    "reason_selected": "highest priority",
                    "priority": 0.9,
                    "expand_pointer": {"object_id": summary["id"]},
                }
            ],
            "selection_policy": "priority-first",
        },
    }
    schema = {
        "id": "showcase-schema",
        "type": "SchemaNote",
        "content": {"rule": "stable procedure"},
        "source_refs": [summary["id"], reflection["id"]],
        "created_at": updated_at,
        "updated_at": updated_at,
        "version": 1,
        "status": "active",
        "priority": 0.7,
        "metadata": {
            "kind": "semantic",
            "evidence_refs": [summary["id"], reflection["id"]],
            "stability_score": 0.8,
            "promotion_source_refs": [summary["id"], reflection["id"]],
        },
    }
    return [raw, episode, summary, reflection, entity, link, workspace, schema]
