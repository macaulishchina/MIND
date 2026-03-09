"""Phase E startup and gate evaluation helpers."""

from __future__ import annotations

import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from mind.fixtures.golden_episode_set import build_golden_episode_set
from mind.fixtures.long_horizon_dev import (
    LongHorizonSequence,
    LongHorizonStep,
    build_long_horizon_dev_v1,
)
from mind.fixtures.retrieval_benchmark import build_phase_d_seed_objects
from mind.kernel.integrity import IntegrityReport, build_integrity_report
from mind.kernel.store import MemoryStore, MemoryStoreFactory, SQLiteMemoryStore

from .audit import (
    PromotionAudit,
    SchemaEvidenceAudit,
    audit_promotion_within_window,
    audit_schema_evidence,
)
from .jobs import (
    OfflineJobKind,
    PromoteSchemaJobPayload,
    ReflectEpisodeJobPayload,
    new_offline_job,
)
from .replay import (
    deterministic_random_decile,
    future_reuse_rate,
    select_replay_targets,
)
from .service import OfflineMaintenanceService


@dataclass(frozen=True)
class LongHorizonSequenceRun:
    sequence_id: str
    step_count: int
    candidate_count: int
    top_decile_ids: tuple[str, ...]
    random_decile_ids: tuple[str, ...]
    top_decile_reuse_rate: float
    random_decile_reuse_rate: float
    tags: tuple[str, ...]
    promotion_target_refs: tuple[str, ...]
    promoted_schema_object_id: str | None
    schema_evidence_precision: float | None
    promotion_precise: bool | None


@dataclass(frozen=True)
class MaintenanceSequenceRun:
    sequence_id: str
    maintenance_enabled: bool
    selected_handle_ids: tuple[tuple[str, ...], ...]
    task_success_rate: float
    gold_fact_coverage: float
    reuse_rate: float
    average_handle_count: float


@dataclass(frozen=True)
class PhaseEStartupResult:
    sequence_count: int
    min_step_count: int
    max_step_count: int
    promotion_sequence_count: int
    audited_schema_count: int
    top_decile_reuse_rate: float
    random_decile_reuse_rate: float
    replay_lift: float
    schema_validation_precision: float
    promotion_precision_at_10: float
    runs: tuple[LongHorizonSequenceRun, ...]

    @property
    def long_horizon_fixture_pass(self) -> bool:
        return self.sequence_count >= 30 and self.min_step_count >= 5 and self.max_step_count <= 10

    @property
    def replay_lift_pass(self) -> bool:
        return self.replay_lift >= 1.5

    @property
    def schema_validation_pass(self) -> bool:
        return self.audited_schema_count > 0 and self.schema_validation_precision >= 0.85

    @property
    def promotion_precision_pass(self) -> bool:
        return self.promotion_sequence_count > 0 and self.promotion_precision_at_10 >= 0.80

    @property
    def phase_e_startup_pass(self) -> bool:
        return (
            self.long_horizon_fixture_pass
            and self.replay_lift_pass
            and self.schema_validation_pass
            and self.promotion_precision_pass
        )


@dataclass(frozen=True)
class PhaseEDevEvalResult:
    sequence_count: int
    step_count: int
    no_maintenance_task_success_rate: float
    maintenance_task_success_rate: float
    no_maintenance_gold_fact_coverage: float
    maintenance_gold_fact_coverage: float
    no_maintenance_reuse_rate: float
    maintenance_reuse_rate: float
    context_cost_ratio: float
    no_maintenance_maintenance_cost_ratio: float
    maintenance_maintenance_cost_ratio: float
    no_maintenance_pollution_rate: float
    maintenance_pollution_rate: float
    no_maintenance_pus: float
    maintenance_pus: float
    pus_improvement: float
    pollution_rate_delta: float
    no_maintenance_runs: tuple[MaintenanceSequenceRun, ...]
    maintenance_runs: tuple[MaintenanceSequenceRun, ...]

    @property
    def e5_pass(self) -> bool:
        return self.pus_improvement >= 0.05 and self.pollution_rate_delta <= 0.02


@dataclass(frozen=True)
class PhaseEGateResult:
    startup_result: PhaseEStartupResult
    dev_eval: PhaseEDevEvalResult
    integrity_report: IntegrityReport
    generated_reflection_count: int
    generated_schema_count: int

    @property
    def e1_pass(self) -> bool:
        return self.integrity_report.source_trace_coverage == 1.0

    @property
    def e2_pass(self) -> bool:
        return self.startup_result.schema_validation_pass

    @property
    def e3_pass(self) -> bool:
        return self.startup_result.replay_lift_pass

    @property
    def e4_pass(self) -> bool:
        return self.startup_result.promotion_precision_pass

    @property
    def e5_pass(self) -> bool:
        return self.dev_eval.e5_pass

    @property
    def phase_e_pass(self) -> bool:
        return self.e1_pass and self.e2_pass and self.e3_pass and self.e4_pass and self.e5_pass


@dataclass(frozen=True)
class _PromotionAuditBundle:
    schema_object_id: str
    schema_audit: SchemaEvidenceAudit
    promotion_audit: PromotionAudit


@dataclass(frozen=True)
class _PreparedPhaseEState:
    sequences: tuple[LongHorizonSequence, ...]
    runs: tuple[LongHorizonSequenceRun, ...]
    promotion_audits: dict[str, _PromotionAuditBundle]
    integrity_report: IntegrityReport
    generated_reflection_ids: tuple[str, ...]


def evaluate_phase_e_startup(
    db_path: str | Path | None = None,
    store_factory: MemoryStoreFactory | None = None,
) -> PhaseEStartupResult:
    """Evaluate the Phase E startup baseline without the full E-5 A/B gate."""

    active_factory = store_factory or _default_store_factory
    if db_path is not None:
        return _run_startup(Path(db_path), active_factory)

    with tempfile.TemporaryDirectory() as tmpdir:
        return _run_startup(Path(tmpdir) / "phase_e.sqlite3", active_factory)


def assert_phase_e_startup(result: PhaseEStartupResult) -> None:
    if not result.long_horizon_fixture_pass:
        raise RuntimeError(
            "Phase E startup failed: LongHorizonDev v1 invalid "
            f"(sequence_count={result.sequence_count}, "
            f"min_step_count={result.min_step_count}, "
            f"max_step_count={result.max_step_count})"
        )
    if not result.replay_lift_pass:
        raise RuntimeError(f"Phase E startup failed: ReplayLift ({result.replay_lift:.2f})")
    if not result.schema_validation_pass:
        raise RuntimeError(
            "Phase E startup failed: SchemaValidationPrecision "
            f"({result.schema_validation_precision:.2f})"
        )
    if not result.promotion_precision_pass:
        raise RuntimeError(
            "Phase E startup failed: PromotionPrecision@10 "
            f"({result.promotion_precision_at_10:.2f})"
        )


def evaluate_phase_e_gate(
    db_path: str | Path | None = None,
    store_factory: MemoryStoreFactory | None = None,
) -> PhaseEGateResult:
    """Evaluate the formal Phase E gate."""

    active_factory = store_factory or _default_store_factory
    if db_path is not None:
        return _run_gate(Path(db_path), active_factory)

    with tempfile.TemporaryDirectory() as tmpdir:
        return _run_gate(Path(tmpdir) / "phase_e_gate.sqlite3", active_factory)


def assert_phase_e_gate(result: PhaseEGateResult) -> None:
    if not result.e1_pass:
        raise RuntimeError(
            "E-1 failed: derived trace coverage "
            f"({result.integrity_report.source_trace_coverage:.2f})"
        )
    if not result.e2_pass:
        raise RuntimeError(
            "E-2 failed: SchemaValidationPrecision "
            f"({result.startup_result.schema_validation_precision:.2f})"
        )
    if not result.e3_pass:
        raise RuntimeError(f"E-3 failed: ReplayLift ({result.startup_result.replay_lift:.2f})")
    if not result.e4_pass:
        raise RuntimeError(
            "E-4 failed: PromotionPrecision@10 "
            f"({result.startup_result.promotion_precision_at_10:.2f})"
        )
    if not result.e5_pass:
        raise RuntimeError(
            "E-5 failed: offline maintenance net benefit "
            f"(pus_improvement={result.dev_eval.pus_improvement:.2f}, "
            f"pollution_rate_delta={result.dev_eval.pollution_rate_delta:.2f})"
        )


def _run_startup(store_path: Path, active_store_factory: MemoryStoreFactory) -> PhaseEStartupResult:
    with active_store_factory(store_path) as store:
        state = _prepare_phase_e_state(store)
    return _build_startup_result(state.runs)


def _run_gate(store_path: Path, active_store_factory: MemoryStoreFactory) -> PhaseEGateResult:
    with active_store_factory(store_path) as store:
        state = _prepare_phase_e_state(store)
        dev_eval = _evaluate_offline_dev_eval(store, state)
    startup_result = _build_startup_result(state.runs)
    return PhaseEGateResult(
        startup_result=startup_result,
        dev_eval=dev_eval,
        integrity_report=state.integrity_report,
        generated_reflection_count=len(state.generated_reflection_ids),
        generated_schema_count=len(state.promotion_audits),
    )


def _prepare_phase_e_state(store: MemoryStore) -> _PreparedPhaseEState:
    store.insert_objects(build_phase_d_seed_objects())
    sequences = tuple(build_long_horizon_dev_v1())
    maintenance_service = OfflineMaintenanceService(store)
    generated_reflection_ids = _run_failure_episode_reflections(maintenance_service)
    promotion_audits = {
        sequence.sequence_id: _run_sequence_promotion_audit(
            store,
            maintenance_service,
            sequence,
        )
        for sequence in sequences
        if sequence.promotion_target_refs
    }
    runs = tuple(
        _evaluate_startup_sequence(
            store,
            sequence,
            promotion_audits.get(sequence.sequence_id),
        )
        for sequence in sequences
    )
    integrity_report = build_integrity_report(store.iter_objects())
    return _PreparedPhaseEState(
        sequences=sequences,
        runs=runs,
        promotion_audits=promotion_audits,
        integrity_report=integrity_report,
        generated_reflection_ids=generated_reflection_ids,
    )


def _build_startup_result(runs: tuple[LongHorizonSequenceRun, ...]) -> PhaseEStartupResult:
    top_rate = round(sum(run.top_decile_reuse_rate for run in runs) / float(len(runs)), 4)
    random_rate = round(sum(run.random_decile_reuse_rate for run in runs) / float(len(runs)), 4)
    schema_precisions = [
        run.schema_evidence_precision for run in runs if run.schema_evidence_precision is not None
    ]
    promotion_precisions = [
        run.promotion_precise for run in runs if run.promotion_precise is not None
    ]
    return PhaseEStartupResult(
        sequence_count=len(runs),
        min_step_count=min(run.step_count for run in runs),
        max_step_count=max(run.step_count for run in runs),
        promotion_sequence_count=sum(bool(run.promotion_target_refs) for run in runs),
        audited_schema_count=len(schema_precisions),
        top_decile_reuse_rate=top_rate,
        random_decile_reuse_rate=random_rate,
        replay_lift=_safe_ratio(top_rate, random_rate),
        schema_validation_precision=round(_average(schema_precisions), 4),
        promotion_precision_at_10=round(
            _average([1.0 if precise else 0.0 for precise in promotion_precisions]),
            4,
        ),
        runs=runs,
    )


def _evaluate_startup_sequence(
    store: MemoryStore,
    sequence: LongHorizonSequence,
    promotion_audit: _PromotionAuditBundle | None,
) -> LongHorizonSequenceRun:
    top_k = max(1, len(sequence.candidate_ids) // 10)
    top_targets = select_replay_targets(store, sequence.candidate_ids, top_k=top_k)
    top_ids = tuple(target.object_id for target in top_targets)
    random_ids = deterministic_random_decile(
        sequence.sequence_id,
        sequence.candidate_ids,
        top_k=top_k,
    )
    return LongHorizonSequenceRun(
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
            job_id=f"phase-e-reflect-{episode.episode_id}",
            job_kind=OfflineJobKind.REFLECT_EPISODE,
            payload=ReflectEpisodeJobPayload(
                episode_id=episode.episode_id,
                focus="offline maintenance reflection",
            ),
        )
        result = maintenance_service.process_job(job, actor="phase_e_gate")
        generated_ids.append(str(result["reflection_object_id"]))
    return tuple(generated_ids)


def _run_sequence_promotion_audit(
    store: MemoryStore,
    maintenance_service: OfflineMaintenanceService,
    sequence: LongHorizonSequence,
) -> _PromotionAuditBundle:
    job = new_offline_job(
        job_id=f"phase-e-promotion-{sequence.sequence_id}",
        job_kind=OfflineJobKind.PROMOTE_SCHEMA,
        payload=PromoteSchemaJobPayload(
            target_refs=list(sequence.promotion_target_refs),
            reason="promote repeated stale-memory pattern",
        ),
    )
    result = maintenance_service.process_job(job, actor="phase_e_gate")
    schema_object_id = str(result["schema_object_id"])
    return _PromotionAuditBundle(
        schema_object_id=schema_object_id,
        schema_audit=audit_schema_evidence(store, schema_object_id),
        promotion_audit=audit_promotion_within_window(store, schema_object_id, sequence),
    )


def _evaluate_offline_dev_eval(
    store: MemoryStore,
    state: _PreparedPhaseEState,
) -> PhaseEDevEvalResult:
    no_maintenance_runs = tuple(
        _evaluate_maintenance_sequence(
            store,
            sequence,
            promoted_schema_object_id=None,
            maintenance_enabled=False,
        )
        for sequence in state.sequences
    )
    maintenance_runs = tuple(
        _evaluate_maintenance_sequence(
            store,
            sequence,
            promoted_schema_object_id=(
                state.promotion_audits[sequence.sequence_id].schema_object_id
                if sequence.sequence_id in state.promotion_audits
                else None
            ),
            maintenance_enabled=True,
        )
        for sequence in state.sequences
    )

    step_count = sum(len(sequence.steps) for sequence in state.sequences)
    generated_object_count = len(state.generated_reflection_ids) + len(state.promotion_audits)
    polluted_generated_count = sum(
        not bundle.schema_audit.supported or not bundle.promotion_audit.precise
        for bundle in state.promotion_audits.values()
    )

    no_task_success = round(
        _average([run.task_success_rate for run in no_maintenance_runs]),
        4,
    )
    maintenance_task_success = round(
        _average([run.task_success_rate for run in maintenance_runs]),
        4,
    )
    no_gold_coverage = round(_average([run.gold_fact_coverage for run in no_maintenance_runs]), 4)
    maintenance_gold_coverage = round(
        _average([run.gold_fact_coverage for run in maintenance_runs]),
        4,
    )
    no_reuse_rate = round(_average([run.reuse_rate for run in no_maintenance_runs]), 4)
    maintenance_reuse_rate = round(_average([run.reuse_rate for run in maintenance_runs]), 4)
    baseline_avg_handle_count = _average([run.average_handle_count for run in no_maintenance_runs])
    maintenance_avg_handle_count = _average([run.average_handle_count for run in maintenance_runs])
    context_cost_ratio = round(
        _safe_ratio(maintenance_avg_handle_count, baseline_avg_handle_count),
        4,
    )

    no_pollution_rate = 0.0
    maintenance_pollution_rate = round(
        _safe_ratio(polluted_generated_count, generated_object_count),
        4,
    )
    no_maintenance_cost_ratio = 1.0
    maintenance_cost_ratio = round(1.0 + _safe_ratio(generated_object_count, step_count), 4)

    no_pus = _compute_pus(
        task_success_rate=no_task_success,
        gold_fact_coverage=no_gold_coverage,
        reuse_rate=no_reuse_rate,
        context_cost_ratio=1.0,
        maintenance_cost_ratio=no_maintenance_cost_ratio,
        pollution_rate=no_pollution_rate,
    )
    maintenance_pus = _compute_pus(
        task_success_rate=maintenance_task_success,
        gold_fact_coverage=maintenance_gold_coverage,
        reuse_rate=maintenance_reuse_rate,
        context_cost_ratio=context_cost_ratio,
        maintenance_cost_ratio=maintenance_cost_ratio,
        pollution_rate=maintenance_pollution_rate,
    )

    return PhaseEDevEvalResult(
        sequence_count=len(state.sequences),
        step_count=step_count,
        no_maintenance_task_success_rate=no_task_success,
        maintenance_task_success_rate=maintenance_task_success,
        no_maintenance_gold_fact_coverage=no_gold_coverage,
        maintenance_gold_fact_coverage=maintenance_gold_coverage,
        no_maintenance_reuse_rate=no_reuse_rate,
        maintenance_reuse_rate=maintenance_reuse_rate,
        context_cost_ratio=context_cost_ratio,
        no_maintenance_maintenance_cost_ratio=no_maintenance_cost_ratio,
        maintenance_maintenance_cost_ratio=maintenance_cost_ratio,
        no_maintenance_pollution_rate=no_pollution_rate,
        maintenance_pollution_rate=maintenance_pollution_rate,
        no_maintenance_pus=no_pus,
        maintenance_pus=maintenance_pus,
        pus_improvement=round(maintenance_pus - no_pus, 4),
        pollution_rate_delta=round(maintenance_pollution_rate - no_pollution_rate, 4),
        no_maintenance_runs=no_maintenance_runs,
        maintenance_runs=maintenance_runs,
    )


def _evaluate_maintenance_sequence(
    store: MemoryStore,
    sequence: LongHorizonSequence,
    *,
    promoted_schema_object_id: str | None,
    maintenance_enabled: bool,
) -> MaintenanceSequenceRun:
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
        covered_needed_ids = _covered_needed_ids(store, selected, step.needed_object_ids)
        step_gold_coverage = _safe_ratio(len(covered_needed_ids), len(step.needed_object_ids))
        gold_coverage_total += step_gold_coverage
        if step_gold_coverage == 1.0:
            task_successes += 1

    handle_counts = Counter(object_id for step in selected_steps for object_id in step)
    reuse_rate = _safe_ratio(
        sum(count >= 2 for count in handle_counts.values()),
        len(handle_counts),
    )
    return MaintenanceSequenceRun(
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
