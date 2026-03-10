"""Answer-level benchmark helpers for workspace evaluation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from mind.fixtures.episode_answer_bench import AnswerKind, EpisodeAnswerBenchCase
from mind.kernel.retrieval import build_search_text, tokenize

from .context_protocol import SerializedContext


@dataclass(frozen=True)
class GeneratedAnswer:
    text: str
    support_ids: tuple[str, ...]


@dataclass(frozen=True)
class AnswerScore:
    task_completion_score: float
    constraint_satisfaction: float
    gold_fact_coverage: float
    answer_faithfulness: float
    answer_quality_score: float
    task_success: bool


def answer_from_raw_topk(
    case: EpisodeAnswerBenchCase,
    context: SerializedContext,
) -> GeneratedAnswer:
    payload = json.loads(context.text)
    objects = list(payload["objects"])

    if case.answer_kind is AnswerKind.TASK_RESULT:
        target = _best_object_match(objects, case.prompt, object_types={"TaskEpisode"})
        if target is None:
            return GeneratedAnswer(text="", support_ids=())
        result = str(target["metadata"].get("result", target["content"].get("result_summary", "")))
        task_id = str(target["metadata"].get("task_id", case.task_id))
        return GeneratedAnswer(text=f"{task_id}: {result}", support_ids=(str(target["id"]),))

    if case.answer_kind is AnswerKind.SUMMARY:
        target = _best_object_match(objects, case.prompt, object_types={"SummaryNote"})
        if target is None:
            return GeneratedAnswer(text="", support_ids=())
        return GeneratedAnswer(
            text=str(target["content"].get("summary", "")),
            support_ids=(str(target["id"]),),
        )

    if case.answer_kind is AnswerKind.RESULT_AND_SUMMARY:
        episode = _best_object_match(objects, case.prompt, object_types={"TaskEpisode"})
        summary = _best_object_match(objects, case.prompt, object_types={"SummaryNote"})
        if episode is None and summary is None:
            return GeneratedAnswer(text="", support_ids=())
        parts: list[str] = []
        support_ids: list[str] = []
        if episode is not None:
            result = str(
                episode["metadata"].get(
                    "result",
                    episode["content"].get("result_summary", ""),
                )
            )
            task_id = str(episode["metadata"].get("task_id", case.task_id))
            parts.append(f"{task_id}: {result}")
            support_ids.append(str(episode["id"]))
        if summary is not None:
            parts.append(str(summary["content"].get("summary", "")))
            support_ids.append(str(summary["id"]))
        return GeneratedAnswer(
            text=" | ".join(part for part in parts if part),
            support_ids=tuple(support_ids),
        )

    if case.answer_kind is AnswerKind.FINAL_RAW:
        candidates = [
            obj
            for obj in objects
            if obj["type"] == "RawRecord"
            and str(obj.get("metadata", {}).get("record_kind", "")) == "assistant_message"
        ]
        if not candidates:
            return GeneratedAnswer(text="", support_ids=())
        target = max(
            candidates,
            key=lambda obj: (
                _keyword_overlap(case.prompt, build_search_text(obj)),
                int(obj.get("metadata", {}).get("timestamp_order", 0)),
                str(obj["id"]),
            ),
        )
        return GeneratedAnswer(
            text=str(target["content"].get("text", "")),
            support_ids=(str(target["id"]),),
        )

    raise RuntimeError(f"unsupported answer kind {case.answer_kind.value}")


def answer_from_workspace(
    case: EpisodeAnswerBenchCase,
    context: SerializedContext,
) -> GeneratedAnswer:
    payload = json.loads(context.text)
    selected_ids = tuple(str(object_id) for object_id in payload["selected_object_ids"])
    raw_slots = payload["slots"]
    if len(raw_slots) != len(selected_ids):
        raise RuntimeError(
            f"workspace slots ({len(raw_slots)}) and "
            f"selected_object_ids ({len(selected_ids)}) length mismatch"
        )
    slots = [
        {
            "object_id": selected_ids[index],
            "summary": str(slot["summary"]),
            "source_refs": tuple(str(ref) for ref in slot["source_refs"]),
        }
        for index, slot in enumerate(raw_slots)
    ]

    if case.answer_kind is AnswerKind.TASK_RESULT:
        target = _best_slot_match(slots, case.prompt)
        if target is None:
            return GeneratedAnswer(text="", support_ids=())
        result = _extract_result(target["summary"])
        return GeneratedAnswer(text=f"{case.task_id}: {result}", support_ids=(target["object_id"],))

    if case.answer_kind is AnswerKind.SUMMARY:
        target = _best_slot_match(slots, case.prompt)
        if target is None:
            return GeneratedAnswer(text="", support_ids=())
        return GeneratedAnswer(text=target["summary"], support_ids=(target["object_id"],))

    if case.answer_kind is AnswerKind.RESULT_AND_SUMMARY:
        task_slot = _best_slot_match(slots, case.prompt, require_result_marker=True)
        summary_candidates = [slot for slot in slots if slot is not task_slot]
        summary_slot = _best_slot_match(summary_candidates, case.prompt)
        parts: list[str] = []
        support_ids: list[str] = []
        if task_slot is not None:
            parts.append(f"{case.task_id}: {_extract_result(task_slot['summary'])}")
            support_ids.append(task_slot["object_id"])
        if summary_slot is not None:
            parts.append(summary_slot["summary"])
            support_ids.append(summary_slot["object_id"])
        return GeneratedAnswer(text=" | ".join(parts), support_ids=tuple(support_ids))

    if case.answer_kind is AnswerKind.FINAL_RAW:
        target = _best_slot_match(slots, case.prompt)
        if target is None:
            return GeneratedAnswer(text="", support_ids=())
        return GeneratedAnswer(text=target["summary"], support_ids=(target["object_id"],))

    raise RuntimeError(f"unsupported answer kind {case.answer_kind.value}")


def score_answer(case: EpisodeAnswerBenchCase, answer: GeneratedAnswer) -> AnswerScore:
    normalized_answer = _normalize(answer.text)
    if not case.required_fragments:
        task_completion_score = 0.0
    else:
        matched_fragments = sum(
            1 for fragment in case.required_fragments if _normalize(fragment) in normalized_answer
        )
        task_completion_score = round(matched_fragments / float(len(case.required_fragments)), 4)

    satisfied_constraints = [
        bool(answer.text.strip()),
        _token_count(answer.text) <= case.max_answer_tokens,
    ]
    if case.answer_kind in {AnswerKind.TASK_RESULT, AnswerKind.RESULT_AND_SUMMARY}:
        satisfied_constraints.append(case.task_id in normalized_answer)
    constraint_satisfaction = round(
        sum(satisfied_constraints) / float(len(satisfied_constraints)),
        4,
    )

    gold_fact_coverage = _coverage(answer.support_ids, case.gold_fact_ids)
    answer_faithfulness = _faithfulness(answer.support_ids, case.gold_fact_ids)
    answer_quality_score = round(
        0.45 * task_completion_score
        + 0.20 * constraint_satisfaction
        + 0.20 * gold_fact_coverage
        + 0.15 * answer_faithfulness,
        4,
    )
    return AnswerScore(
        task_completion_score=task_completion_score,
        constraint_satisfaction=constraint_satisfaction,
        gold_fact_coverage=gold_fact_coverage,
        answer_faithfulness=answer_faithfulness,
        answer_quality_score=answer_quality_score,
        task_success=(task_completion_score == 1.0 and constraint_satisfaction == 1.0),
    )


def _best_object_match(
    objects: list[dict[str, Any]],
    prompt: str,
    *,
    object_types: set[str],
) -> dict[str, Any] | None:
    candidates = [obj for obj in objects if str(obj["type"]) in object_types]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda obj: (
            _keyword_overlap(prompt, build_search_text(obj)),
            str(obj["id"]),
        ),
    )


def _best_slot_match(
    slots: list[dict[str, Any]],
    prompt: str,
    *,
    require_result_marker: bool = False,
) -> dict[str, Any] | None:
    candidates = [
        slot
        for slot in slots
        if not require_result_marker or ("[" in slot["summary"] and "]" in slot["summary"])
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda slot: (
            _keyword_overlap(prompt, f"{slot['object_id']} {slot['summary']}"),
            slot["object_id"],
        ),
    )


def _extract_result(summary: str) -> str:
    match = re.search(r"\[([^\]]+)\]", summary)
    if match is not None:
        return match.group(1).strip().lower()
    return summary.strip().lower()


def _coverage(actual_ids: tuple[str, ...], gold_ids: tuple[str, ...]) -> float:
    if not gold_ids:
        return 0.0
    return round(len(set(actual_ids).intersection(gold_ids)) / float(len(gold_ids)), 4)


def _faithfulness(actual_ids: tuple[str, ...], gold_ids: tuple[str, ...]) -> float:
    if not actual_ids:
        return 0.0
    return round(len(set(actual_ids).intersection(gold_ids)) / float(len(set(actual_ids))), 4)


def _token_count(text: str) -> int:
    return len(text.split()) if text else 0


def _keyword_overlap(left: str, right: str) -> int:
    left_tokens = tokenize(left)
    if not left_tokens:
        return 0
    return len(left_tokens.intersection(tokenize(right)))


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())
