"""Internal helpers for offline assessment evaluation."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from mind.fixtures.golden_episode_set import build_golden_episode_set
from mind.fixtures.long_horizon_dev import LongHorizonSequence, LongHorizonStep
from mind.kernel.store import MemoryStore, SQLiteMemoryStore

from .audit import audit_promotion_within_window, audit_schema_evidence
from .jobs import (
    OfflineJobKind,
    PromoteSchemaJobPayload,
    ReflectEpisodeJobPayload,
    new_offline_job,
)
from .replay import deterministic_random_decile, future_reuse_rate, select_replay_targets
from .service import OfflineMaintenanceService

if TYPE_CHECKING:
    from .assessment import (
        LongHorizonSequenceRun,
        MaintenanceSequenceRun,
        _PromotionAuditBundle,
    )


def _evaluate_startup_sequence(
    store: MemoryStore,
    sequence: LongHorizonSequence,
    promotion_audit: _PromotionAuditBundle | None,
) -> LongHorizonSequenceRun:
    from .assessment import LongHorizonSequenceRun as _Cls

    top_k = max(1, len(sequence.candidate_ids) // 10)
    top_targets = select_replay_targets(store, sequence.candidate_ids, top_k=top_k)
    top_ids = tuple(target.object_id for target in top_targets)
    random_ids = deterministic_random_decile(
        sequence.sequence_id,
        sequence.candidate_ids,
        top_k=top_k,
    )
    return _Cls(
        sequence_id=sequence.sequence_id,
        step_count=len(sequence.steps),
        candidate_count=len(sequence.candidate_ids),
        top_decile_ids=top_ids,
        random_decile_ids=random_ids,
        top_decile_reuse_rate=future_reuse_rate(top_ids, sequence.steps),
        random_decile_reuse_rate=future_reuse_rate(random_ids, sequence.steps),
        tags=sequence.tags,
        promotion_target_refs=sequence.promotion_target_refs,
        promoted_schema_object_id=promotion_audit.schema_object_id if promotion_audit else None,
        schema_evidence_precision=(
            promotion_audit.schema_audit.precision if promotion_audit else None
        ),
        promotion_precise=promotion_audit.promotion_audit.precise if promotion_audit else None,
    )


def _run_failure_episode_reflections(
    maintenance_service: OfflineMaintenanceService,
) -> tuple[str, ...]:
    generated_ids: list[str] = []
    for episode in build_golden_episode_set():
        reflection_id = f"{episode.episode_id}-reflection"
        if not any(obj["id"] == reflection_id for obj in episode.objects):
            continue
        job = new_offline_job(
            job_id=f"offline-reflect-{episode.episode_id}",
            job_kind=OfflineJobKind.REFLECT_EPISODE,
            payload=ReflectEpisodeJobPayload(
                episode_id=episode.episode_id,
                focus="offline maintenance reflection",
            ),
        )
        result = maintenance_service.process_job(job, actor="offline_gate")
        generated_ids.append(str(result["reflection_object_id"]))
    return tuple(generated_ids)


def _run_sequence_promotion_audit(
    store: MemoryStore,
    maintenance_service: OfflineMaintenanceService,
    sequence: LongHorizonSequence,
) -> _PromotionAuditBundle:
    from .assessment import _PromotionAuditBundle as _Cls

    job = new_offline_job(
        job_id=f"phase-e-promotion-{sequence.sequence_id}",
        job_kind=OfflineJobKind.PROMOTE_SCHEMA,
        payload=PromoteSchemaJobPayload(
            target_refs=list(sequence.promotion_target_refs),
            reason="promote repeated stale-memory pattern",
        ),
    )
    result = maintenance_service.process_job(job, actor="offline_gate")
    schema_object_id = str(result["schema_object_id"])
    return _Cls(
        schema_object_id=schema_object_id,
        schema_audit=audit_schema_evidence(store, schema_object_id),
        promotion_audit=audit_promotion_within_window(store, schema_object_id, sequence),
    )


def _evaluate_maintenance_sequence(
    store: MemoryStore,
    sequence: LongHorizonSequence,
    *,
    promoted_schema_object_id: str | None,
    maintenance_enabled: bool,
) -> MaintenanceSequenceRun:
    from .assessment import MaintenanceSequenceRun as _Cls

    candidate_pool = list(sequence.candidate_ids)
    if maintenance_enabled and promoted_schema_object_id is not None:
        candidate_pool.append(promoted_schema_object_id)
    ranking = select_replay_targets(store, tuple(candidate_pool), top_k=len(candidate_pool))
    ranking_by_id = {target.object_id: target.score for target in ranking}

    selected_steps: list[tuple[str, ...]] = []
    task_successes = 0
    gold_coverage_total = 0.0

    for step_index, step in enumerate(sequence.steps):
        selected = _select_step_handles(
            store,
            tuple(candidate_pool),
            step.needed_object_ids,
            ranking_by_id,
            budget=1,
            future_steps=sequence.steps[step_index:],
            prefer_future_coverage=maintenance_enabled,
        )
        selected_steps.append(selected)
        covered_needed = _covered_needed_ids(store, selected, step.needed_object_ids)
        step_gold_coverage = _safe_ratio(len(covered_needed), len(step.needed_object_ids))
        gold_coverage_total += step_gold_coverage
        if step_gold_coverage == 1.0:
            task_successes += 1

    handle_counts = Counter(object_id for step in selected_steps for object_id in step)
    reuse_rate = _safe_ratio(
        sum(count >= 2 for count in handle_counts.values()),
        len(handle_counts),
    )
    return _Cls(
        sequence_id=sequence.sequence_id,
        maintenance_enabled=maintenance_enabled,
        selected_handle_ids=tuple(selected_steps),
        task_success_rate=round(task_successes / float(len(sequence.steps)), 4),
        gold_fact_coverage=round(gold_coverage_total / float(len(sequence.steps)), 4),
        reuse_rate=round(reuse_rate, 4),
        average_handle_count=round(
            sum(len(step) for step in selected_steps) / float(len(sequence.steps)),
            4,
        ),
    )


def _select_step_handles(
    store: MemoryStore,
    candidate_ids: tuple[str, ...],
    needed_object_ids: tuple[str, ...],
    ranking_by_id: dict[str, float],
    *,
    budget: int,
    future_steps: tuple[LongHorizonStep, ...],
    prefer_future_coverage: bool,
) -> tuple[str, ...]:
    selected: list[str] = []
    uncovered = set(needed_object_ids)

    for _ in range(budget):
        best_id: str | None = None
        best_key: tuple[float, float, float, float, str] | None = None
        for object_id in candidate_ids:
            if object_id in selected:
                continue
            coverage = _handle_coverage(store, object_id)
            new_hits = len(coverage.intersection(uncovered))
            total_hits = len(coverage.intersection(needed_object_ids))
            future_hits = (
                _future_coverage_hits(store, object_id, future_steps)
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
        uncovered.difference_update(_handle_coverage(store, best_id))
        if not uncovered:
            break

    return tuple(selected)


def _handle_coverage(store: MemoryStore, object_id: str) -> set[str]:
    obj = store.read_object(object_id)
    coverage = {object_id}
    metadata = obj.get("metadata", {})
    if obj["type"] == "SchemaNote":
        refs = metadata.get("promotion_source_refs") or metadata.get("evidence_refs") or []
        coverage.update(str(ref) for ref in refs)
    return coverage


def _covered_needed_ids(
    store: MemoryStore,
    selected_ids: tuple[str, ...],
    needed_object_ids: tuple[str, ...],
) -> set[str]:
    covered: set[str] = set()
    needed = set(needed_object_ids)
    for object_id in selected_ids:
        covered.update(_handle_coverage(store, object_id).intersection(needed))
    return covered


def _future_coverage_hits(
    store: MemoryStore,
    object_id: str,
    future_steps: tuple[LongHorizonStep, ...],
) -> int:
    coverage = _handle_coverage(store, object_id)
    return sum(len(coverage.intersection(step.needed_object_ids)) for step in future_steps)


def _compute_pus(
    *,
    task_success_rate: float,
    gold_fact_coverage: float,
    reuse_rate: float,
    context_cost_ratio: float,
    maintenance_cost_ratio: float,
    pollution_rate: float,
) -> float:
    return round(
        0.55 * task_success_rate
        + 0.15 * gold_fact_coverage
        + 0.10 * reuse_rate
        - 0.10 * context_cost_ratio
        - 0.05 * maintenance_cost_ratio
        - 0.05 * pollution_rate,
        4,
    )


def _default_store_factory(store_path: Path) -> SQLiteMemoryStore:
    return SQLiteMemoryStore(store_path)


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / float(len(values))


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0 if numerator <= 0 else round(numerator / 0.0001, 4)
    return round(numerator / denominator, 4)
