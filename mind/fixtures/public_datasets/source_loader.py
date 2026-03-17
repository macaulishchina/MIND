"""Load deterministic local public-dataset slices into benchmark fixtures."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

from mind.fixtures.episode_answer_bench import AnswerKind
from mind.fixtures.public_datasets.contracts import (
    NormalizedAnswerSpec,
    NormalizedEpisodeBundle,
    NormalizedLongHorizonSequenceSpec,
    NormalizedLongHorizonStepSpec,
    NormalizedRetrievalSpec,
    PublicDatasetDescriptor,
    PublicDatasetFixture,
)
from mind.fixtures.public_datasets.object_factory import (
    build_base_time,
    build_raw_record,
    build_reflection_note,
    build_summary_note,
    build_task_episode,
)
from mind.primitives.contracts import RetrieveQueryMode


def load_public_dataset_fixture_from_path(
    descriptor: PublicDatasetDescriptor,
    source_path: str | Path,
) -> PublicDatasetFixture:
    """Load one deterministic local source slice into a public dataset fixture."""

    path = Path(source_path)
    payload = _load_payload(path)
    bundles = tuple(_build_bundle(item) for item in _read_mapping_list(payload, "bundles"))
    sequence_specs = tuple(
        _build_sequence_spec(item) for item in _read_mapping_list(payload, "sequence_specs")
    )
    dataset_version = _read_string(payload, "dataset_version")
    fixture_descriptor = descriptor.model_copy(
        update={
            "dataset_version": dataset_version,
            "summary": f"{descriptor.summary} Loaded from local source slice.",
        }
    )
    return PublicDatasetFixture(
        descriptor=fixture_descriptor,
        bundles=bundles,
        sequence_specs=sequence_specs,
    )


def _load_payload(path: Path) -> dict[str, Any]:
    if path.suffix.lower() != ".json":
        raise ValueError(f"public dataset source must be a JSON file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("public dataset source payload must be a JSON object")
    return cast(dict[str, Any], payload)


def _build_bundle(payload: dict[str, Any]) -> NormalizedEpisodeBundle:
    bundle_id = _read_string(payload, "bundle_id")
    task_id = _read_string(payload, "task_id")
    episode_id = _read_string(payload, "episode_id")
    goal = _read_string(payload, "goal")
    result = _read_string(payload, "result")
    summary_text = _read_string(payload, "summary")
    success = _read_bool(payload, "success")
    day_offset = _read_int(payload, "day_offset")
    tags = _read_string_tuple(payload, "tags")
    raw_records_payload = _read_mapping_list(payload, "raw_records")
    if len(raw_records_payload) < 2:
        raise ValueError(f"bundle {bundle_id} must define at least two raw records")

    base_time = build_base_time(day_offset)
    raw_objects: list[dict[str, Any]] = []
    object_refs: dict[str, str] = {
        "episode": episode_id,
        "summary": f"{episode_id}-summary",
    }
    for index, item in enumerate(raw_records_payload, start=1):
        record_id = f"{episode_id}-raw-{index:02d}"
        object_refs[f"record:{index}"] = record_id
        created_at = base_time + timedelta(minutes=index - 1)
        raw_objects.append(
            build_raw_record(
                record_id=record_id,
                episode_id=episode_id,
                record_kind=_read_string(item, "kind"),
                text=_read_string(item, "text"),
                created_at=created_at,
                timestamp_order=index,
            )
        )

    episode_created_at = build_base_time(day_offset)
    episode = build_task_episode(
        episode_id=episode_id,
        task_id=task_id,
        goal=goal,
        result=result,
        success=success,
        created_at=episode_created_at.replace(hour=0, minute=2),
        record_refs=tuple(obj["id"] for obj in raw_objects),
        source_refs=tuple(obj["id"] for obj in raw_objects),
    )
    summary = build_summary_note(
        summary_id=f"{episode_id}-summary",
        episode_id=episode_id,
        summary=summary_text,
        created_at=episode_created_at.replace(hour=0, minute=3),
        input_refs=tuple([*(obj["id"] for obj in raw_objects), episode_id]),
        source_refs=(episode_id,),
    )

    objects: list[dict[str, Any]] = [*raw_objects, episode, summary]
    reflection_payload = payload.get("reflection")
    if reflection_payload is not None:
        if not isinstance(reflection_payload, dict):
            raise ValueError(f"bundle {bundle_id} reflection must be an object")
        reflection_id = f"{episode_id}-reflection"
        object_refs["reflection"] = reflection_id
        objects.append(
            build_reflection_note(
                reflection_id=reflection_id,
                episode_id=episode_id,
                reflection_kind=_read_string(reflection_payload, "kind"),
                claims=_read_string_tuple(reflection_payload, "claims"),
                summary=_read_string(reflection_payload, "summary"),
                created_at=episode_created_at.replace(hour=0, minute=4),
                source_refs=(episode_id, str(summary["id"])),
            )
        )

    retrieval_items = _read_mapping_list(payload, "retrieval_specs")
    retrieval_specs = tuple(_build_retrieval_spec(item, object_refs) for item in retrieval_items)
    answer_items = _read_mapping_list(payload, "answer_specs")
    answer_specs = tuple(_build_answer_spec(item, object_refs) for item in answer_items)

    return NormalizedEpisodeBundle(
        bundle_id=bundle_id,
        task_id=task_id,
        episode_id=episode_id,
        objects=tuple(objects),
        retrieval_specs=retrieval_specs,
        answer_specs=answer_specs,
        tags=tags,
    )


def _build_retrieval_spec(
    payload: dict[str, Any],
    object_refs: dict[str, str],
) -> NormalizedRetrievalSpec:
    vector_scores_payload = payload.get("vector_scores", [])
    if not isinstance(vector_scores_payload, list):
        raise ValueError("retrieval spec vector_scores must be a list")
    vector_scores: list[tuple[str, float]] = []
    for item in vector_scores_payload:
        if not isinstance(item, list | tuple) or len(item) != 2:
            raise ValueError("retrieval spec vector_scores items must be [ref, score]")
        ref, score = item
        if not isinstance(ref, str) or not isinstance(score, int | float):
            raise ValueError("retrieval spec vector_scores items must be [str, float]")
        vector_scores.append((_resolve_object_ref(ref, object_refs), float(score)))
    return NormalizedRetrievalSpec(
        case_key=_read_string(payload, "case_key"),
        query=_read_query(payload),
        query_modes=_read_query_modes(payload),
        filters=_read_mapping(payload, "filters"),
        gold_candidate_ids=_resolve_object_refs(
            _read_string_tuple(payload, "gold_candidate_refs"),
            object_refs,
        ),
        gold_fact_ids=_resolve_object_refs(
            _read_string_tuple(payload, "gold_fact_refs"),
            object_refs,
        ),
        slot_limit=_read_int(payload, "slot_limit"),
        vector_scores=tuple(vector_scores),
    )


def _build_answer_spec(
    payload: dict[str, Any],
    object_refs: dict[str, str],
) -> NormalizedAnswerSpec:
    return NormalizedAnswerSpec(
        case_key=_read_string(payload, "case_key"),
        prompt=_read_string(payload, "prompt"),
        answer_kind=AnswerKind(_read_string(payload, "answer_kind")),
        required_fragments=_read_string_tuple(payload, "required_fragments"),
        gold_fact_ids=_resolve_object_refs(
            _read_string_tuple(payload, "gold_fact_refs"),
            object_refs,
        ),
        gold_memory_refs=_resolve_object_refs(
            _read_string_tuple(payload, "gold_memory_refs"),
            object_refs,
        ),
        max_answer_tokens=_read_int(payload, "max_answer_tokens"),
    )


def _build_sequence_spec(payload: dict[str, Any]) -> NormalizedLongHorizonSequenceSpec:
    steps_payload = _read_mapping_list(payload, "steps")
    return NormalizedLongHorizonSequenceSpec(
        sequence_key=_read_string(payload, "sequence_key"),
        family=_read_string(payload, "family"),
        candidate_ids=_read_string_tuple(payload, "candidate_ids"),
        steps=tuple(
            NormalizedLongHorizonStepSpec(
                step_key=_read_string(item, "step_key"),
                task_id=_read_string(item, "task_id"),
                needed_object_ids=_read_string_tuple(item, "needed_object_ids"),
            )
            for item in steps_payload
        ),
        tags=_read_string_tuple(payload, "tags"),
        maintenance_target_refs=_read_string_tuple(payload, "maintenance_target_refs"),
    )


def _read_query(payload: dict[str, Any]) -> str | dict[str, Any]:
    if "query" not in payload:
        raise ValueError("retrieval spec missing required field 'query'")
    query = payload["query"]
    if not isinstance(query, str | dict):
        raise ValueError("retrieval spec query must be a string or object")
    return query


def _read_query_modes(payload: dict[str, Any]) -> tuple[RetrieveQueryMode, ...]:
    raw_values = _read_string_tuple(payload, "query_modes")
    return tuple(RetrieveQueryMode(value) for value in raw_values)


def _resolve_object_refs(
    refs: tuple[str, ...],
    object_refs: dict[str, str],
) -> tuple[str, ...]:
    return tuple(_resolve_object_ref(ref, object_refs) for ref in refs)


def _resolve_object_ref(ref: str, object_refs: dict[str, str]) -> str:
    try:
        return object_refs[ref]
    except KeyError as exc:
        raise ValueError(f"unknown object ref '{ref}' in local dataset slice") from exc


def _read_mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"field '{key}' must be an object")
    return cast(dict[str, Any], value)


def _read_mapping_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    if key not in payload:
        return []
    value = payload[key]
    if not isinstance(value, list):
        raise ValueError(f"field '{key}' must be a list")
    items: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"field '{key}' must contain only objects")
        items.append(cast(dict[str, Any], item))
    return items


def _read_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"field '{key}' must be a non-empty string")
    return value


def _read_string_tuple(payload: dict[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"field '{key}' must be a list of strings")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ValueError(f"field '{key}' must contain only non-empty strings")
        items.append(item)
    return tuple(items)


def _read_bool(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"field '{key}' must be a boolean")
    return value


def _read_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ValueError(f"field '{key}' must be an integer")
    return value