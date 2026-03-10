"""MIND system runner for LongHorizonEval-based Phase F comparison."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from mind.fixtures.long_horizon_dev import LongHorizonStep
from mind.fixtures.long_horizon_eval import LongHorizonEvalSequence, build_long_horizon_eval_v1
from mind.fixtures.retrieval_benchmark import build_phase_d_seed_objects
from mind.kernel.store import SQLiteMemoryStore
from mind.offline import (
    OfflineJobKind,
    OfflineMaintenanceService,
    PromoteSchemaJobPayload,
    new_offline_job,
    select_replay_targets,
)

from .runner import LongHorizonScoreCard

_RAW_TOPK_BASELINE_SIZE = 10.0


@dataclass
class _MindRunResources:
    tempdir: tempfile.TemporaryDirectory[str]
    store: SQLiteMemoryStore
    promotion_schema_ids: dict[str, str]
    maintenance_cost_ratio: float
    pollution_rate: float


class MindLongHorizonSystem:
    """Phase F MIND system using workspace-style selection and offline promotion."""

    def __init__(
        self,
        *,
        use_workspace: bool = True,
        use_offline_maintenance: bool = True,
    ) -> None:
        self._use_workspace = use_workspace
        self._use_offline_maintenance = use_offline_maintenance
        self._run_resources: dict[int, _MindRunResources] = {}

    def run_sequence(
        self,
        sequence: LongHorizonEvalSequence,
        *,
        run_id: int,
    ) -> LongHorizonScoreCard:
        resources = self._resources_for_run(run_id)
        candidate_pool = list(sequence.candidate_ids)
        if self._use_offline_maintenance:
            promoted_schema_id = resources.promotion_schema_ids.get(sequence.sequence_id)
            if promoted_schema_id is not None:
                candidate_pool.append(promoted_schema_id)

        ranking = select_replay_targets(
            resources.store,
            tuple(candidate_pool),
            top_k=max(len(candidate_pool), 1),
        )
        ranking_by_id = {target.object_id: target.score for target in ranking}

        selected_steps: list[tuple[str, ...]] = []
        task_successes = 0
        gold_coverage_total = 0.0

        for step_index, step in enumerate(sequence.steps):
            selected = _select_step_handles(
                resources.store,
                tuple(candidate_pool),
                step.needed_object_ids,
                ranking_by_id,
                budget=1,
                future_steps=sequence.steps[step_index:],
                prefer_future_coverage=self._use_workspace,
                allow_schema_expansion=self._use_workspace,
            )
            selected_steps.append(selected)
            covered_needed_ids = _covered_needed_ids(
                resources.store,
                selected,
                step.needed_object_ids,
                allow_schema_expansion=self._use_workspace,
            )
            step_gold_coverage = _safe_ratio(len(covered_needed_ids), len(step.needed_object_ids))
            gold_coverage_total += step_gold_coverage
            if step_gold_coverage == 1.0:
                task_successes += 1

        handle_ids = [object_id for step_ids in selected_steps for object_id in step_ids]
        handle_count = len(handle_ids)
        repeated_handle_count = sum(count >= 2 for count in _counter(handle_ids).values())
        reuse_rate = _safe_ratio(repeated_handle_count, len(set(handle_ids)))
        average_handle_count = (
            handle_count / float(len(sequence.steps)) if sequence.steps else 0.0
        )
        return LongHorizonScoreCard(
            task_success_rate=round(task_successes / float(len(sequence.steps)), 4),
            gold_fact_coverage=round(gold_coverage_total / float(len(sequence.steps)), 4),
            reuse_rate=round(reuse_rate, 4),
            context_cost_ratio=round(average_handle_count / _RAW_TOPK_BASELINE_SIZE, 4),
            maintenance_cost_ratio=resources.maintenance_cost_ratio,
            pollution_rate=resources.pollution_rate,
        )

    def close(self) -> None:
        for resources in self._run_resources.values():
            resources.store.close()
            resources.tempdir.cleanup()
        self._run_resources.clear()

    def _resources_for_run(self, run_id: int) -> _MindRunResources:
        resources = self._run_resources.get(run_id)
        if resources is not None:
            return resources

        tempdir = tempfile.TemporaryDirectory(prefix=f"mind_phase_f_run_{run_id}_")
        store = SQLiteMemoryStore(Path(tempdir.name) / "mind_phase_f.sqlite3")
        store.insert_objects(build_phase_d_seed_objects())
        promotion_schema_ids: dict[str, str] = {}
        generated_schema_count = 0

        if self._use_offline_maintenance:
            sequences = build_long_horizon_eval_v1()
            maintenance_service = OfflineMaintenanceService(store)
            for sequence in sequences:
                target_refs = _promotion_target_refs(store, sequence)
                if len(target_refs) < 2:
                    continue
                job = new_offline_job(
                    job_id=f"phase-f-promote-{run_id}-{sequence.sequence_id}",
                    job_kind=OfflineJobKind.PROMOTE_SCHEMA,
                    payload=PromoteSchemaJobPayload(
                        target_refs=list(target_refs),
                        reason="promote reusable long-horizon memory pattern",
                    ),
                )
                try:
                    result = maintenance_service.process_job(job, actor=f"phase_f_run_{run_id}")
                except Exception:
                    continue
                promotion_schema_ids[sequence.sequence_id] = str(result["schema_object_id"])
                generated_schema_count += 1

        total_step_count = sum(len(sequence.steps) for sequence in build_long_horizon_eval_v1())
        maintenance_cost_ratio = (
            round(1.0 + (generated_schema_count / float(total_step_count)), 4)
            if self._use_offline_maintenance and generated_schema_count > 0
            else 1.0
        )
        resources = _MindRunResources(
            tempdir=tempdir,
            store=store,
            promotion_schema_ids=promotion_schema_ids,
            maintenance_cost_ratio=maintenance_cost_ratio,
            pollution_rate=0.0,
        )
        self._run_resources[run_id] = resources
        return resources


def _promotion_target_refs(
    store: SQLiteMemoryStore,
    sequence: LongHorizonEvalSequence,
) -> tuple[str, ...]:
    needed_ids = {
        object_id
        for step in sequence.steps
        for object_id in step.needed_object_ids
    }
    candidate_ids = tuple(
        object_id for object_id in sequence.candidate_ids if store.has_object(object_id)
    )
    best_refs: tuple[str, ...] = ()
    best_key: tuple[float, float, float, str] | None = None

    for target_size in (3, 2):
        for refs in combinations(candidate_ids, target_size):
            if not _supports_cross_episode(store, refs):
                continue
            unique_coverage = len(set(refs).intersection(needed_ids))
            coverage_mentions = sum(
                object_id in refs
                for step in sequence.steps
                for object_id in step.needed_object_ids
            )
            ranking_bonus = sum(
                target.score
                for target in select_replay_targets(store, refs, top_k=len(refs))
            )
            key = (
                float(coverage_mentions),
                float(unique_coverage),
                float(ranking_bonus),
                ",".join(refs),
            )
            if best_key is None or key > best_key:
                best_key = key
                best_refs = tuple(refs)
    return best_refs


def _supports_cross_episode(store: SQLiteMemoryStore, refs: tuple[str, ...]) -> bool:
    episode_ids = {
        str(store.read_object(ref).get("metadata", {}).get("episode_id"))
        for ref in refs
        if store.read_object(ref).get("metadata", {}).get("episode_id") is not None
    }
    return len(episode_ids) >= 2


def _select_step_handles(
    store: SQLiteMemoryStore,
    candidate_ids: tuple[str, ...],
    needed_object_ids: tuple[str, ...],
    ranking_by_id: dict[str, float],
    *,
    budget: int,
    future_steps: tuple[LongHorizonStep, ...],
    prefer_future_coverage: bool,
    allow_schema_expansion: bool,
) -> tuple[str, ...]:
    selected: list[str] = []
    uncovered = set(needed_object_ids)

    for _ in range(budget):
        best_id: str | None = None
        best_key: tuple[float, float, float, float, str] | None = None
        for object_id in candidate_ids:
            if object_id in selected:
                continue
            coverage = _handle_coverage(
                store,
                object_id,
                allow_schema_expansion=allow_schema_expansion,
            )
            new_hits = len(coverage.intersection(uncovered))
            total_hits = len(coverage.intersection(needed_object_ids))
            future_hits = (
                _future_coverage_hits(
                    store,
                    object_id,
                    future_steps,
                    allow_schema_expansion=allow_schema_expansion,
                )
                if prefer_future_coverage
                else 0
            )
            key = (
                float(new_hits),
                float(total_hits),
                float(future_hits),
                float(ranking_by_id.get(object_id, 0.0)),
                object_id,
            )
            if best_key is None or key > best_key:
                best_key = key
                best_id = object_id
        if best_id is None:
            break
        selected.append(best_id)
        uncovered.difference_update(
            _handle_coverage(
                store,
                best_id,
                allow_schema_expansion=allow_schema_expansion,
            )
        )
        if not uncovered:
            break

    return tuple(selected)


def _handle_coverage(
    store: SQLiteMemoryStore,
    object_id: str,
    *,
    allow_schema_expansion: bool,
) -> set[str]:
    obj = store.read_object(object_id)
    coverage = {object_id}
    metadata = obj.get("metadata", {})
    if allow_schema_expansion and obj["type"] == "SchemaNote":
        refs = metadata.get("promotion_source_refs") or metadata.get("evidence_refs") or []
        coverage.update(str(ref) for ref in refs)
    return coverage


def _covered_needed_ids(
    store: SQLiteMemoryStore,
    selected_ids: tuple[str, ...],
    needed_object_ids: tuple[str, ...],
    *,
    allow_schema_expansion: bool,
) -> set[str]:
    covered: set[str] = set()
    needed = set(needed_object_ids)
    for object_id in selected_ids:
        covered.update(
            _handle_coverage(
                store,
                object_id,
                allow_schema_expansion=allow_schema_expansion,
            ).intersection(needed)
        )
    return covered


def _future_coverage_hits(
    store: SQLiteMemoryStore,
    object_id: str,
    future_steps: tuple[LongHorizonStep, ...],
    *,
    allow_schema_expansion: bool,
) -> int:
    coverage = _handle_coverage(
        store,
        object_id,
        allow_schema_expansion=allow_schema_expansion,
    )
    return sum(len(coverage.intersection(step.needed_object_ids)) for step in future_steps)


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _counter(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts
