"""LoCoMo raw-import compilation helpers."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from mind.fixtures.public_datasets.object_factory import build_base_time


def compile_locomo_local_slice(
    examples: list[dict[str, Any]],
    *,
    example_ids: tuple[str, ...],
    max_items: int | None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Select, build bundles, and build sequence for LoCoMo examples.

    Returns ``(bundles, sequence_spec)``.
    """

    selected_examples = _select_locomo_examples(
        examples,
        example_ids=example_ids,
        max_items=max_items,
    )
    bundles = [
        _build_locomo_bundle_payload(example, index=index)
        for index, example in enumerate(selected_examples, start=1)
    ]
    sequence_spec = _build_locomo_sequence_payload(bundles)
    return bundles, sequence_spec


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def _select_locomo_examples(
    examples: list[dict[str, Any]],
    *,
    example_ids: tuple[str, ...],
    max_items: int | None,
) -> list[dict[str, Any]]:
    eligible_examples = [
        example
        for example in examples
        if _is_supported_locomo_example(example)
    ]
    example_by_id = {
        _read_required_string(example, "episode_id"): example
        for example in eligible_examples
    }

    if example_ids:
        selected_examples: list[dict[str, Any]] = []
        for example_id in example_ids:
            example = example_by_id.get(example_id)
            if example is None:
                raise ValueError(
                    f"unknown or unsupported LoCoMo episode id: {example_id}"
                )
            selected_examples.append(example)
    else:
        limit = max_items if max_items is not None else 2
        selected_examples = eligible_examples[:limit]

    if not selected_examples:
        raise ValueError(
            "no supported LoCoMo episodes were selected from the raw inputs"
        )
    return selected_examples


# ---------------------------------------------------------------------------
# Bundle building
# ---------------------------------------------------------------------------


def _build_locomo_bundle_payload(
    example: dict[str, Any],
    *,
    index: int,
) -> dict[str, object]:
    example_id = _read_required_string(example, "episode_id")
    task_id = _read_required_string(example, "task_id")
    goal = _read_required_string(example, "goal")
    result = _read_required_string(example, "result")
    summary = _read_required_string(example, "summary")
    recall_question = _read_required_string(example, "recall_question")
    answer_prompt = _read_required_string(example, "answer_prompt")
    answer_kind = _read_required_string(example, "answer_kind")
    required_fragments = _read_string_list(example, "required_fragments")
    turns = _read_turns(example)
    reflection = _read_locomo_reflection(example)
    include_time_window = bool(example.get("include_time_window", False))
    day_offset = _read_required_int(example, "day_offset")
    base_time = build_base_time(day_offset)
    episode_id = f"locomo-raw-episode-{example_id}"

    retrieval_specs: list[dict[str, object]] = [
        {
            "case_key": f"{example_id}_keyword",
            "query": recall_question,
            "query_modes": ["keyword"],
            "filters": {"object_types": ["TaskEpisode", "SummaryNote"]},
            "gold_candidate_refs": ["episode", "summary"],
            "gold_fact_refs": ["episode", "summary"],
            "slot_limit": 2,
        }
    ]
    if include_time_window:
        retrieval_specs.append(
            {
                "case_key": f"{example_id}_time_window",
                "query": {
                    "start": base_time.isoformat(),
                    "end": (
                        base_time + timedelta(minutes=3, seconds=30)
                    ).isoformat(),
                },
                "query_modes": ["time_window"],
                "filters": {
                    "object_types": [
                        "RawRecord",
                        "TaskEpisode",
                        "SummaryNote",
                    ],
                },
                "gold_candidate_refs": [
                    "record:1",
                    "record:2",
                    "episode",
                    "summary",
                ],
                "gold_fact_refs": [
                    "record:1",
                    "record:2",
                    "episode",
                ],
                "slot_limit": 4,
            }
        )

    return {
        "bundle_id": f"locomo_raw_bundle_{example_id}",
        "task_id": task_id,
        "episode_id": episode_id,
        "day_offset": day_offset,
        "goal": goal,
        "result": result,
        "success": True,
        "summary": summary,
        "reflection": reflection,
        "raw_records": turns,
        "retrieval_specs": retrieval_specs,
        "answer_specs": [
            {
                "case_key": f"{example_id}_keyword",
                "prompt": answer_prompt,
                "answer_kind": answer_kind,
                "required_fragments": required_fragments,
                "gold_fact_refs": ["episode", "summary"],
                "gold_memory_refs": ["episode", "summary"],
                "max_answer_tokens": 18,
            }
        ],
        "tags": ["public_dataset", "locomo", "raw_import"],
    }


# ---------------------------------------------------------------------------
# Sequence building
# ---------------------------------------------------------------------------


def _build_locomo_sequence_payload(
    bundles: list[dict[str, object]],
) -> dict[str, object]:
    candidate_ids: list[str] = []
    steps: list[dict[str, object]] = []
    maintenance_target_refs: list[str] = []
    for index, bundle in enumerate(bundles, start=1):
        episode_id = str(bundle["episode_id"])
        task_id = str(bundle["task_id"])
        summary_id = f"{episode_id}-summary"
        reflection_id = f"{episode_id}-reflection"
        candidate_ids.extend((summary_id, episode_id, reflection_id))
        maintenance_target_refs.append(reflection_id)
        steps.append(
            {
                "step_key": f"step_{index:02d}",
                "task_id": task_id,
                "needed_object_ids": [summary_id],
            }
        )

    episode_ids = [str(bundle["episode_id"]) for bundle in bundles]
    summary_ids = [
        f"{episode_id}-summary" for episode_id in episode_ids
    ]
    combined_task_id = "+".join(
        str(bundle["task_id"]) for bundle in bundles
    )
    steps.extend(
        (
            {
                "step_key": f"step_{len(steps) + 1:02d}",
                "task_id": combined_task_id,
                "needed_object_ids": episode_ids,
            },
            {
                "step_key": f"step_{len(steps) + 2:02d}",
                "task_id": combined_task_id,
                "needed_object_ids": summary_ids,
            },
        )
    )
    if bundles:
        steps.insert(
            min(3, len(steps)),
            {
                "step_key": f"step_{len(steps) + 1:02d}",
                "task_id": str(bundles[-1]["task_id"]),
                "needed_object_ids": [
                    f"{episode_ids[0]}-reflection"
                ],
            },
        )

    return {
        "sequence_key": "travel_followup_raw_import",
        "family": "conversation_memory",
        "candidate_ids": candidate_ids,
        "steps": steps,
        "tags": ["public_dataset", "locomo", "raw_import"],
        "maintenance_target_refs": maintenance_target_refs,
    }


# ---------------------------------------------------------------------------
# Turn & reflection parsing
# ---------------------------------------------------------------------------


def _read_turns(example: dict[str, Any]) -> list[dict[str, str]]:
    example_id = _read_required_string(example, "episode_id")
    turns = example.get("turns")
    if not isinstance(turns, list) or len(turns) < 2:
        raise ValueError(
            f"LoCoMo example {example_id} must define at least two turns"
        )
    parsed_turns: list[dict[str, str]] = []
    for item in turns:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        text = item.get("text")
        if (
            isinstance(kind, str)
            and isinstance(text, str)
            and kind
            and text
        ):
            parsed_turns.append({"kind": kind, "text": text})
    if len(parsed_turns) < 2:
        raise ValueError(
            f"LoCoMo example {example_id} must define at least two "
            "valid turns"
        )
    return parsed_turns


def _read_locomo_reflection(
    example: dict[str, Any],
) -> dict[str, object]:
    example_id = _read_required_string(example, "episode_id")
    reflection = example.get("reflection")
    if not isinstance(reflection, dict):
        raise ValueError(
            f"LoCoMo example {example_id} must define a reflection object"
        )
    kind = reflection.get("kind")
    claims = reflection.get("claims")
    summary = reflection.get("summary")
    if not isinstance(kind, str) or not kind:
        raise ValueError(
            "LoCoMo reflection kind must be a non-empty string"
        )
    if not isinstance(summary, str) or not summary:
        raise ValueError(
            "LoCoMo reflection summary must be a non-empty string"
        )
    if (
        not isinstance(claims, list)
        or not claims
        or not all(isinstance(item, str) for item in claims)
    ):
        raise ValueError(
            "LoCoMo reflection claims must be a non-empty string list"
        )
    return {
        "kind": kind,
        "claims": claims,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Eligibility check
# ---------------------------------------------------------------------------


def _is_supported_locomo_example(example: dict[str, Any]) -> bool:
    try:
        _read_required_string(example, "episode_id")
        _read_required_string(example, "task_id")
        _read_required_string(example, "goal")
        _read_required_string(example, "result")
        _read_required_string(example, "summary")
        _read_required_string(example, "recall_question")
        _read_required_string(example, "answer_prompt")
        _read_required_string(example, "answer_kind")
        _read_required_int(example, "day_offset")
        _read_string_list(example, "required_fragments")
        _read_turns(example)
        _read_locomo_reflection(example)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
# Shared low-level helpers
# ---------------------------------------------------------------------------


def _read_required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"field '{key}' must be a non-empty string")
    return value.strip()


def _read_required_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ValueError(f"field '{key}' must be an integer")
    return value


def _read_string_list(
    payload: dict[str, Any], key: str,
) -> list[str]:
    value = payload.get(key)
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise ValueError(
            f"field '{key}' must be a non-empty list of strings"
        )
    return list(value)
