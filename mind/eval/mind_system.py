"""MIND system runner for LongHorizonEval-based benchmark evaluation."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from mind.fixtures.long_horizon_eval import LongHorizonEvalSequence, build_long_horizon_eval_v1
from mind.fixtures.retrieval_benchmark import build_canonical_seed_objects
from mind.kernel.store import SQLiteMemoryStore
from mind.offline import (
    OfflineJobKind,
    OfflineMaintenanceService,
    PromoteSchemaJobPayload,
    new_offline_job,
    select_replay_targets,
)

from .runner import LongHorizonScoreCard
from .strategy import FixedRuleMindStrategy, MindStrategy, covered_needed_ids

_RAW_TOPK_BASELINE_SIZE = 10.0


@dataclass
class _MindRunResources:
    tempdir: tempfile.TemporaryDirectory[str]
    store: SQLiteMemoryStore
    promotion_schema_ids: dict[str, str]
    base_object_count: int
    generated_schema_count: int
    total_object_count: int
    storage_cost_ratio: float
    maintenance_cost_ratio: float
    pollution_rate: float


@dataclass(frozen=True)
class MindRunCostSnapshot:
    run_id: int
    strategy_id: str
    base_object_count: int
    generated_schema_count: int
    total_object_count: int
    storage_cost_ratio: float


class MindLongHorizonSystem:
    """MIND system using workspace-style selection and offline promotion."""

    def __init__(
        self,
        *,
        use_workspace: bool = True,
        use_offline_maintenance: bool = True,
        strategy: MindStrategy | None = None,
    ) -> None:
        self._use_workspace = use_workspace
        self._use_offline_maintenance = use_offline_maintenance
        self._strategy = strategy or FixedRuleMindStrategy(
            prefer_future_coverage=use_workspace,
            allow_schema_expansion=use_workspace,
        )
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
            decision = self._strategy.select_step_handles(
                store=resources.store,
                sequence=sequence,
                step_index=step_index,
                step=step,
                candidate_ids=tuple(candidate_pool),
                ranking_by_id=ranking_by_id,
            )
            selected = decision.selected_ids
            selected_steps.append(selected)
            step_covered_needed_ids = covered_needed_ids(
                resources.store,
                selected,
                step.needed_object_ids,
                allow_schema_expansion=decision.allow_schema_expansion,
            )
            step_gold_coverage = _safe_ratio(
                len(step_covered_needed_ids),
                len(step.needed_object_ids),
            )
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

    def cost_snapshot(self, run_id: int) -> MindRunCostSnapshot:
        resources = self._run_resources.get(run_id)
        if resources is None:
            raise KeyError(f"run_id {run_id} has not been executed")
        return MindRunCostSnapshot(
            run_id=run_id,
            strategy_id=self._strategy.strategy_id,
            base_object_count=resources.base_object_count,
            generated_schema_count=resources.generated_schema_count,
            total_object_count=resources.total_object_count,
            storage_cost_ratio=resources.storage_cost_ratio,
        )

    def _resources_for_run(self, run_id: int) -> _MindRunResources:
        resources = self._run_resources.get(run_id)
        if resources is not None:
            return resources

        tempdir = tempfile.TemporaryDirectory(prefix=f"mind_benchmark_run_{run_id}_")
        store = SQLiteMemoryStore(Path(tempdir.name) / "mind_benchmark.sqlite3")
        seed_objects = build_canonical_seed_objects()
        base_object_count = len(seed_objects)
        store.insert_objects(seed_objects)
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
                    result = maintenance_service.process_job(job, actor=f"benchmark_run_{run_id}")
                except Exception:
                    continue
                promotion_schema_ids[sequence.sequence_id] = str(result["schema_object_id"])
                generated_schema_count += 1

        total_step_count = sum(len(sequence.steps) for sequence in build_long_horizon_eval_v1())
        total_object_count = base_object_count + generated_schema_count
        storage_cost_ratio = (
            round(total_object_count / float(base_object_count), 4)
            if base_object_count > 0
            else 1.0
        )
        maintenance_cost_ratio = (
            round(1.0 + (generated_schema_count / float(total_step_count)), 4)
            if self._use_offline_maintenance and generated_schema_count > 0
            else 1.0
        )
        resources = _MindRunResources(
            tempdir=tempdir,
            store=store,
            promotion_schema_ids=promotion_schema_ids,
            base_object_count=base_object_count,
            generated_schema_count=generated_schema_count,
            total_object_count=total_object_count,
            storage_cost_ratio=storage_cost_ratio,
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


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _counter(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts
