"""Baseline system runners for benchmark comparison."""

from __future__ import annotations

from collections import Counter
from typing import Any

from mind.fixtures.long_horizon_dev import LongHorizonStep
from mind.fixtures.long_horizon_eval import LongHorizonEvalSequence
from mind.fixtures.retrieval_benchmark import build_canonical_seed_objects
from mind.kernel.retrieval import (
    build_query_embedding,
    keyword_score,
    latest_objects,
    vector_score,
)

from .runner import LongHorizonScoreCard

_RAW_TOPK_BASELINE_SIZE = 10.0


class NoMemoryBaselineSystem:
    """Zero-memory baseline used for benchmark comparison."""

    def run_sequence(
        self,
        sequence: LongHorizonEvalSequence,
        *,
        run_id: int,
    ) -> LongHorizonScoreCard:
        del run_id
        selected_steps = tuple(() for _ in sequence.steps)
        return _score_sequence(sequence, selected_steps)


class FixedSummaryMemoryBaselineSystem:
    """Summary-only fixed memory baseline."""

    def __init__(self) -> None:
        self._objects = _latest_object_map()

    def run_sequence(
        self,
        sequence: LongHorizonEvalSequence,
        *,
        run_id: int,
    ) -> LongHorizonScoreCard:
        del run_id
        selected_steps = tuple(
            self._select_step_handles(sequence, step)
            for step in sequence.steps
        )
        return _score_sequence(sequence, selected_steps, objects=self._objects)

    def _select_step_handles(
        self,
        sequence: LongHorizonEvalSequence,
        step: LongHorizonStep,
    ) -> tuple[str, ...]:
        summary_candidates = [
            self._objects[object_id]
            for object_id in sequence.candidate_ids
            if object_id in self._objects and self._objects[object_id]["type"] == "SummaryNote"
        ]
        if not summary_candidates:
            return ()
        budget = 2 if sequence.family == "cross_episode_pair" else 1
        query = _step_query(sequence, step)
        ranked = sorted(
            summary_candidates,
            key=lambda obj: (keyword_score(query, obj), obj["updated_at"], obj["id"]),
            reverse=True,
        )
        return tuple(obj["id"] for obj in ranked[:budget])


class PlainRagBaselineSystem:
    """Naive retrieval baseline without workspace or offline maintenance."""

    def __init__(self) -> None:
        self._objects = _latest_object_map()

    def run_sequence(
        self,
        sequence: LongHorizonEvalSequence,
        *,
        run_id: int,
    ) -> LongHorizonScoreCard:
        selected_steps = tuple(
            self._select_step_handles(sequence, step, run_id=run_id)
            for step in sequence.steps
        )
        return _score_sequence(sequence, selected_steps, objects=self._objects)

    def _select_step_handles(
        self,
        sequence: LongHorizonEvalSequence,
        step: LongHorizonStep,
        *,
        run_id: int,
    ) -> tuple[str, ...]:
        candidate_objects = [
            self._objects[object_id]
            for object_id in sequence.candidate_ids
            if object_id in self._objects
        ]
        if not candidate_objects:
            return ()
        query = _step_query(sequence, step)
        query_embedding = build_query_embedding(query)
        budget = 2 if "+" in step.task_id or sequence.family == "cross_episode_pair" else 1
        ranked = sorted(
            candidate_objects,
            key=lambda obj: self._ranking_key(
                obj,
                query=query,
                query_embedding=query_embedding,
                run_id=run_id,
            ),
            reverse=True,
        )
        return tuple(obj["id"] for obj in ranked[:budget])

    def _ranking_key(
        self,
        obj: dict[str, Any],
        *,
        query: str,
        query_embedding: tuple[float, ...],
        run_id: int,
    ) -> tuple[float, float, float, str]:
        type_bonus = {
            "TaskEpisode": 0.12,
            "ReflectionNote": 0.08,
            "SummaryNote": 0.06,
            "RawRecord": 0.02,
            "SchemaNote": 0.01,
        }.get(str(obj["type"]), 0.0)
        run_bias = 0.001 * float(run_id)
        return (
            keyword_score(query, obj) + vector_score(query_embedding, obj) + type_bonus + run_bias,
            float(obj["priority"]),
            float(len(_handle_coverage(obj))),
            str(obj["id"]),
        )


def _latest_object_map() -> dict[str, dict[str, Any]]:
    return {obj["id"]: obj for obj in latest_objects(build_canonical_seed_objects())}


def _score_sequence(
    sequence: LongHorizonEvalSequence,
    selected_steps: tuple[tuple[str, ...], ...],
    *,
    objects: dict[str, dict[str, Any]] | None = None,
) -> LongHorizonScoreCard:
    object_map = objects or {}
    task_successes = 0
    gold_coverage_total = 0.0
    handle_counts = Counter(object_id for step_ids in selected_steps for object_id in step_ids)

    for step, selected_ids in zip(sequence.steps, selected_steps, strict=True):
        covered_needed_ids = _covered_needed_ids(object_map, selected_ids, step.needed_object_ids)
        step_gold_coverage = _safe_ratio(len(covered_needed_ids), len(step.needed_object_ids))
        gold_coverage_total += step_gold_coverage
        if step_gold_coverage == 1.0:
            task_successes += 1

    reuse_rate = _safe_ratio(
        sum(count >= 2 for count in handle_counts.values()),
        len(handle_counts),
    )
    average_handle_count = (
        sum(len(step_ids) for step_ids in selected_steps) / float(len(sequence.steps))
        if sequence.steps
        else 0.0
    )
    context_cost_ratio = round(average_handle_count / _RAW_TOPK_BASELINE_SIZE, 4)
    return LongHorizonScoreCard(
        task_success_rate=round(task_successes / float(len(sequence.steps)), 4),
        gold_fact_coverage=round(gold_coverage_total / float(len(sequence.steps)), 4),
        reuse_rate=round(reuse_rate, 4),
        context_cost_ratio=context_cost_ratio,
        maintenance_cost_ratio=1.0,
        pollution_rate=0.0,
    )


def _step_query(sequence: LongHorizonEvalSequence, step: LongHorizonStep) -> str:
    return " ".join(
        [
            sequence.sequence_id,
            sequence.family,
            " ".join(sequence.tags),
            step.step_id,
            step.task_id,
        ]
    )


def _handle_coverage(obj: dict[str, Any]) -> set[str]:
    coverage = {str(obj["id"])}
    metadata = obj.get("metadata", {})
    if obj["type"] == "SchemaNote":
        refs = metadata.get("promotion_source_refs") or metadata.get("evidence_refs") or []
        coverage.update(str(ref) for ref in refs)
    return coverage


def _covered_needed_ids(
    objects: dict[str, dict[str, Any]],
    selected_ids: tuple[str, ...],
    needed_object_ids: tuple[str, ...],
) -> set[str]:
    covered: set[str] = set()
    needed = set(needed_object_ids)
    for object_id in selected_ids:
        obj = objects.get(object_id)
        if obj is None:
            continue
        covered.update(_handle_coverage(obj).intersection(needed))
    return covered


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
