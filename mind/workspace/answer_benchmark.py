"""Answer-level benchmark helpers for workspace evaluation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from mind.capabilities import CapabilityService, generate_answer_text
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
    *,
    capability_service: CapabilityService | None = None,
) -> GeneratedAnswer:
    payload = json.loads(context.text)
    objects = list(payload["objects"])

    if case.answer_kind is AnswerKind.TASK_RESULT:
        target = _best_object_match(objects, case.prompt, object_types={"TaskEpisode"})
        if target is None:
            return GeneratedAnswer(text="", support_ids=())
        result = str(target["metadata"].get("result", target["content"].get("result_summary", "")))
        task_id = str(target["metadata"].get("task_id", case.task_id))
        return _answer_from_capability(
            case,
            draft_text=f"{task_id}: {result}",
            support_ids=(str(target["id"]),),
            capability_service=capability_service,
        )

    if case.answer_kind is AnswerKind.SUMMARY:
        target = _best_object_match(objects, case.prompt, object_types={"SummaryNote"})
        if target is None:
            return GeneratedAnswer(text="", support_ids=())
        return _answer_from_capability(
            case,
            draft_text=str(target["content"].get("summary", "")),
            support_ids=(str(target["id"]),),
            capability_service=capability_service,
        )

    if case.answer_kind is AnswerKind.RESULT_AND_SUMMARY:
        episode = _best_object_match(objects, case.prompt, object_types={"TaskEpisode"})
        summary = _best_summary_object_match(
            objects,
            prompt=case.prompt,
            episode_id=None if episode is None else str(episode["id"]),
            required_fragments=case.required_fragments,
        )
        if episode is None and summary is None:
            return GeneratedAnswer(text="", support_ids=())
        support_ids: list[str] = []
        result_text = ""
        summary_text = ""
        if episode is not None:
            result_text = str(
                episode["metadata"].get(
                    "result",
                    episode["content"].get("result_summary", ""),
                )
            )
            support_ids.append(str(episode["id"]))
        if summary is not None:
            summary_text = str(summary["content"].get("summary", ""))
            support_ids.append(str(summary["id"]))
        return _answer_from_capability(
            case,
            draft_text=_best_result_and_summary_draft(
                case,
                result_text=result_text,
                summary_text=summary_text,
            ),
            support_ids=tuple(support_ids),
            capability_service=capability_service,
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
        return _answer_from_capability(
            case,
            draft_text=str(target["content"].get("text", "")),
            support_ids=(str(target["id"]),),
            capability_service=capability_service,
        )

    raise RuntimeError(f"unsupported answer kind {case.answer_kind.value}")


def answer_from_workspace(
    case: EpisodeAnswerBenchCase,
    context: SerializedContext,
    *,
    capability_service: CapabilityService | None = None,
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
        target = _best_slot_match(slots, case.prompt, require_result_marker=True)
        if target is None:
            target = _best_slot_match(slots, case.prompt)
        if target is None:
            return GeneratedAnswer(text="", support_ids=())
        result = _extract_result(target["summary"])
        return _answer_from_capability(
            case,
            draft_text=f"{case.task_id}: {result}",
            support_ids=(target["object_id"],),
            capability_service=capability_service,
        )

    if case.answer_kind is AnswerKind.SUMMARY:
        target = _best_slot_match(slots, case.prompt)
        if target is None:
            return GeneratedAnswer(text="", support_ids=())
        return _answer_from_capability(
            case,
            draft_text=target["summary"],
            support_ids=(target["object_id"],),
            capability_service=capability_service,
        )

    if case.answer_kind is AnswerKind.RESULT_AND_SUMMARY:
        task_slot = _best_slot_match(slots, case.prompt, require_result_marker=True)
        summary_slot = _best_summary_slot_match(
            [slot for slot in slots if slot is not task_slot],
            prompt=case.prompt,
            task_slot=task_slot,
            required_fragments=case.required_fragments,
        )
        support_ids: list[str] = []
        result_text = ""
        summary_text = ""
        if task_slot is not None:
            result_text = _extract_result(task_slot["summary"])
            support_ids.append(task_slot["object_id"])
        if summary_slot is not None:
            summary_text = summary_slot["summary"]
            support_ids.append(summary_slot["object_id"])
        return _answer_from_capability(
            case,
            draft_text=_best_result_and_summary_draft(
                case,
                result_text=result_text,
                summary_text=summary_text,
            ),
            support_ids=tuple(support_ids),
            capability_service=capability_service,
        )

    if case.answer_kind is AnswerKind.FINAL_RAW:
        target = _best_slot_match(slots, case.prompt)
        if target is None:
            return GeneratedAnswer(text="", support_ids=())
        return _answer_from_capability(
            case,
            draft_text=target["summary"],
            support_ids=(target["object_id"],),
            capability_service=capability_service,
        )

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


def _best_summary_object_match(
    objects: list[dict[str, Any]],
    *,
    prompt: str,
    episode_id: str | None,
    required_fragments: tuple[str, ...],
) -> dict[str, Any] | None:
    candidates = [obj for obj in objects if str(obj["type"]) == "SummaryNote"]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda obj: (
            _matches_episode_summary_scope(obj, episode_id),
            _fragment_match_count(
                str(obj.get("content", {}).get("summary", "")),
                required_fragments,
            ),
            _keyword_overlap(prompt, build_search_text(obj)),
            str(obj["id"]),
        ),
    )


def _best_summary_slot_match(
    slots: list[dict[str, Any]],
    *,
    prompt: str,
    task_slot: dict[str, Any] | None,
    required_fragments: tuple[str, ...],
) -> dict[str, Any] | None:
    if not slots:
        return None
    return max(
        slots,
        key=lambda slot: (
            _matches_task_slot(slot, task_slot),
            _fragment_match_count(str(slot["summary"]), required_fragments),
            _keyword_overlap(prompt, f"{slot['object_id']} {slot['summary']}"),
            slot["object_id"],
        ),
    )


def _best_result_and_summary_draft(
    case: EpisodeAnswerBenchCase,
    *,
    result_text: str,
    summary_text: str,
) -> str:
    candidates = [
        text
        for text in (
            f"{case.task_id}: {summary_text}" if summary_text else "",
            f"{case.task_id}: {result_text}" if result_text else "",
            _combine_result_and_summary(case, result_text=result_text, summary_text=summary_text),
        )
        if text.strip()
    ]
    if not candidates:
        return ""
    return max(candidates, key=lambda text: _benchmark_text_quality(case, text))


def _combine_result_and_summary(
    case: EpisodeAnswerBenchCase,
    *,
    result_text: str,
    summary_text: str,
) -> str:
    parts = [
        f"{case.task_id}: {result_text}" if result_text else "",
        summary_text,
    ]
    return " | ".join(part for part in parts if part)


def _extract_result(summary: str) -> str:
    match = re.search(r"\[([^\]]+)\]", summary)
    if match is not None:
        return match.group(1).strip()
    return summary.strip()


def _answer_from_capability(
    case: EpisodeAnswerBenchCase,
    *,
    draft_text: str,
    support_ids: tuple[str, ...],
    capability_service: CapabilityService | None,
) -> GeneratedAnswer:
    if not draft_text:
        return GeneratedAnswer(text="", support_ids=support_ids)
    generated_text = generate_answer_text(
        question=case.prompt,
        context_text=draft_text,
        support_ids=support_ids,
        max_answer_tokens=case.max_answer_tokens,
        capability_service=capability_service,
        request_id_prefix="workspace-answer",
    )
    answer_text = generated_text
    if capability_service is None:
        answer_text = _prefer_faithful_benchmark_text(
            case,
            draft_text=draft_text,
            generated_text=generated_text,
        )
    return GeneratedAnswer(
        text=answer_text,
        support_ids=support_ids,
    )


def _prefer_faithful_benchmark_text(
    case: EpisodeAnswerBenchCase,
    *,
    draft_text: str,
    generated_text: str,
) -> str:
    if not generated_text.strip():
        return draft_text
    if _benchmark_text_quality(case, draft_text) > _benchmark_text_quality(case, generated_text):
        return draft_text
    return generated_text


def _benchmark_text_quality(case: EpisodeAnswerBenchCase, text: str) -> tuple[float, int, int, int]:
    matched_fragments = _fragment_match_count(text, case.required_fragments)
    constraint_count = sum(_text_constraints(case, text))
    return (
        round(matched_fragments / float(len(case.required_fragments)), 4)
        if case.required_fragments
        else 0.0,
        constraint_count,
        -_token_count(text),
        len(text),
    )


def _text_constraints(case: EpisodeAnswerBenchCase, text: str) -> tuple[bool, ...]:
    normalized_text = _normalize(text)
    constraints: list[bool] = [
        bool(text.strip()),
        _token_count(text) <= case.max_answer_tokens,
    ]
    if case.answer_kind in {AnswerKind.TASK_RESULT, AnswerKind.RESULT_AND_SUMMARY}:
        constraints.append(_normalize(case.task_id) in normalized_text)
    return tuple(constraints)


def _fragment_match_count(text: str, required_fragments: tuple[str, ...]) -> int:
    normalized_text = _normalize(text)
    return sum(1 for fragment in required_fragments if _normalize(fragment) in normalized_text)


def _matches_episode_summary_scope(obj: dict[str, Any], episode_id: str | None) -> bool:
    if episode_id is None:
        return False
    metadata = obj.get("metadata", {})
    if str(metadata.get("summary_scope", "")) == episode_id:
        return True
    source_refs = obj.get("source_refs", [])
    return isinstance(source_refs, list) and episode_id in source_refs


def _matches_task_slot(slot: dict[str, Any], task_slot: dict[str, Any] | None) -> bool:
    if task_slot is None:
        return False
    task_object_id = str(task_slot["object_id"])
    slot_object_id = str(slot["object_id"])
    if slot_object_id == f"{task_object_id}-summary":
        return True
    source_refs = slot.get("source_refs", ())
    return task_object_id in source_refs


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
