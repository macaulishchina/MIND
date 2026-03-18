"""HotpotQA raw-import compilation helpers."""

from __future__ import annotations

from typing import Any


def compile_hotpotqa_local_slice(
    examples: list[dict[str, Any]],
    *,
    example_ids: tuple[str, ...],
    max_items: int | None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Select, build bundles, and build sequence for HotpotQA examples.

    Returns ``(bundles, sequence_spec)``.
    """

    selected_examples = _select_hotpotqa_examples(
        examples,
        example_ids=example_ids,
        max_items=max_items,
    )
    bundles = [
        _build_hotpotqa_bundle_payload(example, index=index)
        for index, example in enumerate(selected_examples, start=1)
    ]
    sequence_spec = _build_hotpotqa_sequence_payload(bundles)
    return bundles, sequence_spec


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def _select_hotpotqa_examples(
    examples: list[dict[str, Any]],
    *,
    example_ids: tuple[str, ...],
    max_items: int | None,
) -> list[dict[str, Any]]:
    eligible_examples = [
        example
        for example in examples
        if _is_supported_hotpotqa_example(example)
    ]
    example_by_id = {
        _read_required_string(example, "_id"): example
        for example in eligible_examples
    }

    if example_ids:
        selected_examples: list[dict[str, Any]] = []
        for example_id in example_ids:
            example = example_by_id.get(example_id)
            if example is None:
                raise ValueError(
                    f"unknown or unsupported HotpotQA example id: {example_id}"
                )
            selected_examples.append(example)
    else:
        limit = max_items if max_items is not None else 2
        selected_examples = eligible_examples[:limit]

    if not selected_examples:
        raise ValueError(
            "no supported HotpotQA examples were selected from the raw inputs"
        )
    return selected_examples


# ---------------------------------------------------------------------------
# Bundle building
# ---------------------------------------------------------------------------


def _build_hotpotqa_bundle_payload(
    example: dict[str, Any],
    *,
    index: int,
) -> dict[str, object]:
    example_id = _read_required_string(example, "_id")
    question = _read_required_string(example, "question")
    answer = _read_required_string(example, "answer")
    evidence_text = _build_hotpotqa_evidence_text(example)
    evidence_titles = _hotpotqa_support_titles(example)
    episode_id = f"hotpotqa-raw-episode-{example_id}"
    task_id = f"hotpotqa-raw-task-{example_id}"
    title_fragments = [
        title for title in evidence_titles[:2] if title not in answer
    ]
    summary_text = f"{evidence_text} Therefore the answer is {answer}."

    return {
        "bundle_id": f"hotpotqa_raw_bundle_{example_id}",
        "task_id": task_id,
        "episode_id": episode_id,
        "day_offset": 120 + index,
        "goal": f"Answer the multi-hop question: {question}",
        "result": answer,
        "success": True,
        "summary": summary_text,
        "raw_records": [
            {
                "kind": "user_message",
                "text": question,
            },
            {
                "kind": "tool_result",
                "text": f"Supporting facts: {evidence_text}",
            },
        ],
        "retrieval_specs": [
            {
                "case_key": f"{example_id}_answer",
                "query": question,
                "query_modes": ["keyword"],
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
                "gold_fact_refs": ["record:2", "episode", "summary"],
                "slot_limit": 4,
            }
        ],
        "answer_specs": [
            {
                "case_key": f"{example_id}_answer",
                "prompt": (
                    f"Answer the multi-hop question: {question}"
                ),
                "answer_kind": "result_and_summary",
                "required_fragments": [answer, *title_fragments],
                "gold_fact_refs": ["record:2", "episode", "summary"],
                "gold_memory_refs": ["episode", "summary"],
                "max_answer_tokens": 24,
            }
        ],
        "tags": ["public_dataset", "hotpotqa", "raw_import"],
    }


# ---------------------------------------------------------------------------
# Sequence building
# ---------------------------------------------------------------------------


def _build_hotpotqa_sequence_payload(
    bundles: list[dict[str, object]],
) -> dict[str, object]:
    candidate_ids: list[str] = []
    steps: list[dict[str, object]] = []
    for index, bundle in enumerate(bundles, start=1):
        episode_id = str(bundle["episode_id"])
        task_id = str(bundle["task_id"])
        summary_id = f"{episode_id}-summary"
        evidence_id = f"{episode_id}-raw-02"
        candidate_ids.extend((summary_id, episode_id, evidence_id))
        steps.append(
            {
                "step_key": f"step_{index:02d}",
                "task_id": task_id,
                "needed_object_ids": [summary_id],
            }
        )

    episode_ids = [str(bundle["episode_id"]) for bundle in bundles]
    evidence_ids = [f"{episode_id}-raw-02" for episode_id in episode_ids]
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
                "needed_object_ids": evidence_ids,
            },
        )
    )

    return {
        "sequence_key": "evidence_chain_raw_import",
        "family": "multi_hop_reasoning",
        "candidate_ids": candidate_ids,
        "steps": steps,
        "tags": ["public_dataset", "hotpotqa", "raw_import"],
        "maintenance_target_refs": [],
    }


# ---------------------------------------------------------------------------
# Evidence text
# ---------------------------------------------------------------------------


def _build_hotpotqa_evidence_text(example: dict[str, Any]) -> str:
    example_id = _read_required_string(example, "_id")
    context_by_title = _hotpotqa_context_by_title(example)
    snippets: list[str] = []
    for title, sentence_index in _hotpotqa_support_pairs(example):
        sentences = context_by_title.get(title)
        if sentences is None:
            raise ValueError(
                "HotpotQA example "
                f"{example_id} references missing context title {title}"
            )
        if sentence_index < 0 or sentence_index >= len(sentences):
            raise ValueError(
                "HotpotQA example "
                f"{example_id} references invalid sentence index "
                f"{sentence_index} for {title}"
            )
        snippets.append(f"{title}: {sentences[sentence_index]}")

    if not snippets:
        raise ValueError(
            f"HotpotQA example {example_id} did not yield any supporting "
            "snippets"
        )
    return " ".join(snippets)


# ---------------------------------------------------------------------------
# Support pair helpers
# ---------------------------------------------------------------------------


def _hotpotqa_support_pairs(
    example: dict[str, Any],
) -> list[tuple[str, int]]:
    supporting_facts = example.get("supporting_facts")
    if not isinstance(supporting_facts, list):
        return []
    pairs: list[tuple[str, int]] = []
    for item in supporting_facts:
        if not isinstance(item, list | tuple) or len(item) != 2:
            continue
        title, sentence_index = item
        if isinstance(title, str) and isinstance(sentence_index, int):
            pairs.append((title, sentence_index))
    return pairs


def _hotpotqa_support_titles(example: dict[str, Any]) -> list[str]:
    titles: list[str] = []
    for title, _ in _hotpotqa_support_pairs(example):
        if title not in titles:
            titles.append(title)
    return titles


def _hotpotqa_context_by_title(
    example: dict[str, Any],
) -> dict[str, list[str]]:
    context = example.get("context")
    if not isinstance(context, list):
        raise ValueError(
            "HotpotQA example "
            f"{_read_required_string(example, '_id')} "
            "must define a context list"
        )
    context_by_title: dict[str, list[str]] = {}
    for item in context:
        if not isinstance(item, list | tuple) or len(item) != 2:
            continue
        title, sentences = item
        if not isinstance(title, str) or not isinstance(sentences, list):
            continue
        if not all(isinstance(sentence, str) for sentence in sentences):
            continue
        context_by_title[title] = list(sentences)
    return context_by_title


# ---------------------------------------------------------------------------
# Eligibility check
# ---------------------------------------------------------------------------


def _is_supported_hotpotqa_example(example: dict[str, Any]) -> bool:
    try:
        _read_required_string(example, "_id")
        _read_required_string(example, "question")
        _read_required_string(example, "answer")
    except ValueError:
        return False
    return bool(_hotpotqa_support_pairs(example)) and bool(
        _hotpotqa_context_by_title(example)
    )


# ---------------------------------------------------------------------------
# Shared low-level helpers
# ---------------------------------------------------------------------------


def _read_required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"field '{key}' must be a non-empty string")
    return value.strip()
