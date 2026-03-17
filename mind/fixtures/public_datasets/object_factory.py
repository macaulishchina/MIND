"""Helpers for building valid benchmark objects from public dataset slices."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from mind.kernel.schema import SchemaValidationError, validate_object


def build_base_time(day_offset: int) -> datetime:
    """Return a deterministic UTC anchor time for a dataset slice."""

    return datetime(2026, 2, 1, tzinfo=UTC) + timedelta(days=day_offset)


def build_raw_record(
    *,
    record_id: str,
    episode_id: str,
    record_kind: str,
    text: str,
    created_at: datetime,
    timestamp_order: int,
) -> dict[str, Any]:
    """Build one valid `RawRecord` object."""

    return _validated_object(
        {
            "id": record_id,
            "type": "RawRecord",
            "content": {"text": text},
            "source_refs": [],
            "created_at": created_at.isoformat(),
            "updated_at": created_at.isoformat(),
            "version": 1,
            "status": "active",
            "priority": 0.4,
            "metadata": {
                "record_kind": record_kind,
                "episode_id": episode_id,
                "timestamp_order": timestamp_order,
            },
        }
    )


def build_task_episode(
    *,
    episode_id: str,
    task_id: str,
    goal: str,
    result: str,
    success: bool,
    created_at: datetime,
    record_refs: tuple[str, ...],
    source_refs: tuple[str, ...],
) -> dict[str, Any]:
    """Build one valid `TaskEpisode` object."""

    return _validated_object(
        {
            "id": episode_id,
            "type": "TaskEpisode",
            "content": {
                "goal": goal,
                "result": result,
                "task_id": task_id,
            },
            "source_refs": list(source_refs),
            "created_at": created_at.isoformat(),
            "updated_at": created_at.isoformat(),
            "version": 1,
            "status": "active",
            "priority": 0.8,
            "metadata": {
                "task_id": task_id,
                "goal": goal,
                "result": result,
                "success": success,
                "record_refs": list(record_refs),
            },
        }
    )


def build_summary_note(
    *,
    summary_id: str,
    episode_id: str,
    summary: str,
    created_at: datetime,
    input_refs: tuple[str, ...],
    source_refs: tuple[str, ...],
) -> dict[str, Any]:
    """Build one valid `SummaryNote` object."""

    return _validated_object(
        {
            "id": summary_id,
            "type": "SummaryNote",
            "content": {"summary": summary},
            "source_refs": list(source_refs),
            "created_at": created_at.isoformat(),
            "updated_at": created_at.isoformat(),
            "version": 1,
            "status": "active",
            "priority": 0.7,
            "metadata": {
                "summary_scope": episode_id,
                "input_refs": list(input_refs),
                "compression_ratio_estimate": 0.5,
            },
        }
    )


def build_reflection_note(
    *,
    reflection_id: str,
    episode_id: str,
    reflection_kind: str,
    claims: tuple[str, ...],
    summary: str,
    created_at: datetime,
    source_refs: tuple[str, ...],
) -> dict[str, Any]:
    """Build one valid `ReflectionNote` object."""

    return _validated_object(
        {
            "id": reflection_id,
            "type": "ReflectionNote",
            "content": {
                "summary": summary,
                "claims": list(claims),
            },
            "source_refs": list(source_refs),
            "created_at": created_at.isoformat(),
            "updated_at": created_at.isoformat(),
            "version": 1,
            "status": "active",
            "priority": 0.6,
            "metadata": {
                "episode_id": episode_id,
                "reflection_kind": reflection_kind,
                "claims": list(claims),
            },
        }
    )


def _validated_object(obj: dict[str, Any]) -> dict[str, Any]:
    errors = validate_object(obj)
    if errors:
        raise SchemaValidationError("; ".join(errors))
    return obj
