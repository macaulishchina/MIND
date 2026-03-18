"""Unified evaluation helpers for public-dataset fixtures."""

from __future__ import annotations

import json
import statistics
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mind.capabilities import CapabilityService, resolve_capability_provider_config
from mind.eval.runner import (
    LongHorizonBenchmarkRun,
    LongHorizonBenchmarkRunner,
    LongHorizonScoreCard,
)
from mind.eval.strategy import (
    FixedRuleMindStrategy,
    MindStrategy,
    OptimizedMindStrategy,
    PublicDatasetMindStrategy,
    covered_needed_ids,
)
from mind.fixtures.episode_answer_bench import EpisodeAnswerBenchCase
from mind.fixtures.long_horizon_eval import LongHorizonEvalManifest, LongHorizonEvalSequence
from mind.fixtures.public_datasets.registry import (
    build_public_dataset_answer_cases,
    build_public_dataset_fixture,
    build_public_dataset_long_horizon_manifest,
    build_public_dataset_long_horizon_sequences,
    build_public_dataset_objects,
    build_public_dataset_retrieval_cases,
)
from mind.fixtures.retrieval_benchmark import RetrievalBenchmarkCase
from mind.kernel.retrieval import build_query_embedding
from mind.kernel.store import MemoryStore, SQLiteMemoryStore
from mind.offline import select_replay_targets
from mind.primitives.contracts import (
    PrimitiveExecutionContext,
    PrimitiveOutcome,
    RetrieveResponse,
)
from mind.primitives.service import PrimitiveService
from mind.workspace.answer_benchmark import (
    AnswerScore,
    answer_from_raw_topk,
    answer_from_workspace,
    score_answer,
)
from mind.workspace.builder import WorkspaceBuilder, WorkspaceBuildError
from mind.workspace.context_protocol import build_raw_topk_context, build_workspace_context
from mind.workspace.smoke import RetrievalBenchmarkRun


@dataclass(frozen=True)
class PublicDatasetWorkspaceSummary:
    """Aggregate retrieval and answer metrics for one public dataset."""

    case_count: int
    answer_case_count: int
    keyword_case_count: int
    time_window_case_count: int
    vector_case_count: int
    candidate_recall_at_20: float
    workspace_gold_fact_coverage: float
    workspace_answer_quality_score: float
    workspace_task_success_rate: float
    median_token_cost_ratio: float


@dataclass(frozen=True)
class PublicDatasetLongHorizonSummary:
    """Aggregate long-horizon metrics for one public dataset."""

    sequence_count: int
    average_task_success_rate: float
    average_gold_fact_coverage: float
    average_reuse_rate: float
    average_context_cost_ratio: float
    average_maintenance_cost_ratio: float
    average_pollution_rate: float
    average_pus: float


@dataclass(frozen=True)
class PublicDatasetEvaluationReport:
    """Unified evaluation report for one public dataset fixture."""

    dataset_name: str
    source_path: str | None
    fixture_name: str
    fixture_hash: str
    object_count: int
    retrieval_case_count: int
    answer_case_count: int
    long_horizon_sequence_count: int
    answer_provider: str
    answer_model: str
    answer_provider_configured: bool
    long_horizon_strategy: str
    workspace: PublicDatasetWorkspaceSummary
    long_horizon: PublicDatasetLongHorizonSummary
    findings: tuple[str, ...]


def evaluate_public_dataset(
    dataset_name: str,
    *,
    source_path: str | Path | None = None,
    provider_selection: Mapping[str, object] | Any | None = None,
    long_horizon_strategy: str = "public-dataset",
) -> PublicDatasetEvaluationReport:
    """Evaluate one public dataset fixture through unified benchmark summaries."""

    fixture = build_public_dataset_fixture(dataset_name, source_path=source_path)
    manifest = build_public_dataset_long_horizon_manifest(dataset_name, source_path=source_path)
    objects = build_public_dataset_objects(dataset_name, source_path=source_path)
    retrieval_cases = build_public_dataset_retrieval_cases(dataset_name, source_path=source_path)
    answer_cases = build_public_dataset_answer_cases(dataset_name, source_path=source_path)
    sequences = build_public_dataset_long_horizon_sequences(dataset_name, source_path=source_path)
    capability_service = CapabilityService(
        provider_config=resolve_capability_provider_config(selection=provider_selection),
    )
    strategy = _long_horizon_strategy(long_horizon_strategy)
    workspace_summary = _evaluate_workspace_summary(
        objects,
        retrieval_cases,
        answer_cases,
        capability_service=capability_service,
    )
    long_horizon_run = _evaluate_long_horizon_summary(
        objects,
        sequences,
        manifest,
        strategy=strategy,
    )
    provider_summary = capability_service.provider_config.redacted_summary()
    long_horizon_summary = PublicDatasetLongHorizonSummary(
        sequence_count=long_horizon_run.sequence_count,
        average_task_success_rate=long_horizon_run.average_task_success_rate,
        average_gold_fact_coverage=long_horizon_run.average_gold_fact_coverage,
        average_reuse_rate=long_horizon_run.average_reuse_rate,
        average_context_cost_ratio=long_horizon_run.average_context_cost_ratio,
        average_maintenance_cost_ratio=long_horizon_run.average_maintenance_cost_ratio,
        average_pollution_rate=long_horizon_run.average_pollution_rate,
        average_pus=long_horizon_run.average_pus,
    )
    report = PublicDatasetEvaluationReport(
        dataset_name=dataset_name,
        source_path=str(source_path) if source_path is not None else None,
        fixture_name=fixture.fixture_name(),
        fixture_hash=manifest.fixture_hash,
        object_count=len(objects),
        retrieval_case_count=len(retrieval_cases),
        answer_case_count=len(answer_cases),
        long_horizon_sequence_count=len(sequences),
        answer_provider=str(provider_summary["provider"]),
        answer_model=str(provider_summary["model"]),
        answer_provider_configured=bool(provider_summary["auth"]["configured"]),
        long_horizon_strategy=strategy.strategy_id,
        workspace=workspace_summary,
        long_horizon=long_horizon_summary,
        findings=_build_findings(
            workspace_summary,
            long_horizon_summary,
            provider=provider_summary["provider"],
            provider_configured=bool(provider_summary["auth"]["configured"]),
        ),
    )
    return report


def write_public_dataset_evaluation_report_json(
    path: str | Path,
    report: PublicDatasetEvaluationReport,
) -> Path:
    """Persist a public-dataset evaluation report as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_report_to_dict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def _evaluate_workspace_summary(
    objects: list[dict[str, object]],
    retrieval_cases: list[RetrievalBenchmarkCase],
    answer_cases: list[EpisodeAnswerBenchCase],
    *,
    capability_service: CapabilityService,
) -> PublicDatasetWorkspaceSummary:
    answer_case_map = {case.case_id: case for case in answer_cases}

    with tempfile.TemporaryDirectory(prefix="public_dataset_workspace_") as tmpdir:
        with SQLiteMemoryStore(Path(tmpdir) / "workspace.sqlite3") as store:
            store.insert_objects(objects)
            service = PrimitiveService(store, query_embedder=build_query_embedding)
            builder = WorkspaceBuilder(store)
            runs = [
                _evaluate_retrieval_case(
                    case=case,
                    answer_case=answer_case_map.get(case.case_id),
                    service=service,
                    builder=builder,
                    capability_service=capability_service,
                    store=store,
                )
                for case in retrieval_cases
            ]

    keyword_case_count = sum(_has_mode(run, "keyword") for run in runs)
    time_window_case_count = sum(_has_mode(run, "time_window") for run in runs)
    vector_case_count = sum(_has_mode(run, "vector") for run in runs)
    answer_runs = [run for run in runs if run.case_id in answer_case_map]
    return PublicDatasetWorkspaceSummary(
        case_count=len(retrieval_cases),
        answer_case_count=len(answer_cases),
        keyword_case_count=keyword_case_count,
        time_window_case_count=time_window_case_count,
        vector_case_count=vector_case_count,
        candidate_recall_at_20=round(
            sum(run.candidate_recall_at_20 for run in runs) / float(len(runs)),
            4,
        ) if runs else 0.0,
        workspace_gold_fact_coverage=round(
            sum(run.workspace_gold_fact_coverage for run in runs) / float(len(runs)),
            4,
        ) if runs else 0.0,
        workspace_answer_quality_score=round(
            sum(run.workspace_answer_quality_score for run in answer_runs)
            / float(len(answer_runs)),
            4,
        ) if answer_runs else 0.0,
        workspace_task_success_rate=round(
            sum(run.workspace_task_success for run in answer_runs) / float(len(answer_runs)),
            4,
        ) if answer_runs else 0.0,
        median_token_cost_ratio=round(
            float(statistics.median(run.token_cost_ratio for run in runs)),
            4,
        ) if runs else 0.0,
    )


def _evaluate_long_horizon_summary(
    objects: list[dict[str, object]],
    sequences: list[LongHorizonEvalSequence],
    manifest: LongHorizonEvalManifest,
    *,
    strategy: MindStrategy,
) -> LongHorizonBenchmarkRun:
    runner = LongHorizonBenchmarkRunner(sequences=sequences, manifest=manifest)
    system = _FixtureLongHorizonSystem(objects, strategy=strategy)
    try:
        return runner.run_once(system_id="public_dataset_fixture", system=system, run_id=1)
    finally:
        system.close()


def _evaluate_retrieval_case(
    *,
    case: RetrievalBenchmarkCase,
    answer_case: EpisodeAnswerBenchCase | None,
    service: PrimitiveService,
    builder: WorkspaceBuilder,
    capability_service: CapabilityService,
    store: MemoryStore,
) -> RetrievalBenchmarkRun:
    result = service.retrieve(
        {
            "query": case.query,
            "query_modes": [mode.value for mode in case.query_modes],
            "budget": {"max_cost": 1000.0, "max_candidates": 20},
            "filters": case.filters,
        },
        PrimitiveExecutionContext(
            actor="public_dataset_eval",
            budget_scope_id=f"public_dataset::{case.case_id}",
        ),
    )
    response = (
        RetrieveResponse.model_validate(result.response)
        if result.outcome is PrimitiveOutcome.SUCCESS and result.response is not None
        else None
    )
    candidate_ids = tuple(response.candidate_ids if response is not None else ())
    raw_top20_ids = candidate_ids[:20]
    raw_gold_fact_coverage = _coverage(raw_top20_ids, case.gold_fact_ids)
    raw_context = build_raw_topk_context(store, raw_top20_ids)
    raw_answer_score = (
        score_answer(
            answer_case,
            answer_from_raw_topk(
                answer_case,
                raw_context,
                capability_service=capability_service,
            ),
        )
        if answer_case is not None
        else _empty_answer_score()
    )

    workspace_selected_ids: tuple[str, ...] = ()
    workspace_gold_fact_coverage = 0.0
    workspace_answer_score = _empty_answer_score()
    workspace_token_cost = raw_context.token_count
    token_cost_ratio = 1.0 if raw_context.token_count > 0 else 0.0
    workspace_task_success_proxy = False
    slot_discipline = False
    source_ref_coverage = False
    if response is not None and candidate_ids:
        try:
            workspace_result = builder.build(
                task_id=case.task_id,
                candidate_ids=list(response.candidate_ids),
                candidate_scores=list(response.scores),
                slot_limit=case.slot_limit,
                workspace_id=f"public-dataset-{case.case_id}",
            )
        except WorkspaceBuildError:
            workspace_result = None
        if workspace_result is not None:
            workspace = workspace_result.workspace
            slots = workspace["metadata"]["slots"]
            workspace_selected_ids = workspace_result.selected_ids
            workspace_fact_ids = _workspace_fact_ids(workspace_selected_ids, slots)
            workspace_gold_fact_coverage = _coverage(workspace_fact_ids, case.gold_fact_ids)
            workspace_context = build_workspace_context(workspace)
            workspace_token_cost = workspace_context.token_count
            if answer_case is not None:
                workspace_answer_score = score_answer(
                    answer_case,
                    answer_from_workspace(
                        answer_case,
                        workspace_context,
                        capability_service=capability_service,
                    ),
                )
            token_cost_ratio = _safe_ratio(workspace_token_cost, raw_context.token_count)
            workspace_task_success_proxy = workspace_gold_fact_coverage == 1.0
            slot_discipline = len(slots) <= case.slot_limit
            source_ref_coverage = all(bool(slot["source_refs"]) for slot in slots)

    return RetrievalBenchmarkRun(
        case_id=case.case_id,
        query_modes=case.query_modes,
        outcome=result.outcome,
        candidate_ids=candidate_ids,
        raw_top20_ids=raw_top20_ids,
        workspace_selected_ids=workspace_selected_ids,
        candidate_recall_at_20=_coverage(candidate_ids[:20], case.gold_candidate_ids),
        raw_top20_gold_fact_coverage=raw_gold_fact_coverage,
        workspace_gold_fact_coverage=workspace_gold_fact_coverage,
        raw_top20_token_cost=raw_context.token_count,
        workspace_token_cost=workspace_token_cost,
        token_cost_ratio=token_cost_ratio,
        raw_top20_task_completion_score=raw_answer_score.task_completion_score,
        workspace_task_completion_score=workspace_answer_score.task_completion_score,
        raw_top20_answer_quality_score=raw_answer_score.answer_quality_score,
        workspace_answer_quality_score=workspace_answer_score.answer_quality_score,
        raw_top20_task_success=raw_answer_score.task_success,
        workspace_task_success=workspace_answer_score.task_success,
        raw_top20_task_success_proxy=raw_gold_fact_coverage == 1.0,
        workspace_task_success_proxy=workspace_task_success_proxy,
        workspace_slot_discipline=slot_discipline,
        workspace_source_ref_coverage=source_ref_coverage,
    )


def _workspace_fact_ids(
    selected_ids: tuple[str, ...],
    slots: list[dict[str, object]],
) -> tuple[str, ...]:
    fact_ids = set(selected_ids)
    for slot in slots:
        evidence_refs = slot.get("evidence_refs")
        if not isinstance(evidence_refs, list):
            continue
        for ref in evidence_refs:
            if isinstance(ref, str) and ref:
                fact_ids.add(ref)
    return tuple(sorted(fact_ids))


class _FixtureLongHorizonSystem:
    """Long-horizon system runner backed directly by a public fixture object set."""

    def __init__(self, objects: list[dict[str, object]], *, strategy: MindStrategy) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="public_dataset_long_horizon_")
        self._store = SQLiteMemoryStore(Path(self._tempdir.name) / "long_horizon.sqlite3")
        self._store.insert_objects(objects)
        self._strategy = strategy

    def run_sequence(
        self,
        sequence: LongHorizonEvalSequence,
        *,
        run_id: int,
    ) -> LongHorizonScoreCard:
        del run_id
        candidate_pool = tuple(
            object_id for object_id in sequence.candidate_ids if self._store.has_object(object_id)
        )
        ranking = select_replay_targets(
            self._store,
            candidate_pool,
            top_k=max(len(candidate_pool), 1),
        )
        ranking_by_id = {target.object_id: target.score for target in ranking}
        selected_steps: list[tuple[str, ...]] = []
        task_successes = 0
        gold_coverage_total = 0.0

        for step_index, step in enumerate(sequence.steps):
            decision = self._strategy.select_step_handles(
                store=self._store,
                sequence=sequence,
                step_index=step_index,
                step=step,
                candidate_ids=candidate_pool,
                ranking_by_id=ranking_by_id,
            )
            selected_steps.append(decision.selected_ids)
            covered_ids = covered_needed_ids(
                self._store,
                decision.selected_ids,
                step.needed_object_ids,
                allow_schema_expansion=decision.allow_schema_expansion,
            )
            step_coverage = _safe_ratio(len(covered_ids), len(step.needed_object_ids))
            gold_coverage_total += step_coverage
            if step_coverage == 1.0:
                task_successes += 1

        selected_object_ids = [object_id for step_ids in selected_steps for object_id in step_ids]
        distinct_selected_ids = set(selected_object_ids)
        repeated_handle_count = sum(
            selected_object_ids.count(object_id) >= 2 for object_id in distinct_selected_ids
        )
        average_handle_count = (
            len(selected_object_ids) / float(len(sequence.steps)) if sequence.steps else 0.0
        )
        reuse_rate = _safe_ratio(repeated_handle_count, len(distinct_selected_ids))
        return LongHorizonScoreCard(
            task_success_rate=round(task_successes / float(len(sequence.steps)), 4),
            gold_fact_coverage=round(gold_coverage_total / float(len(sequence.steps)), 4),
            reuse_rate=round(reuse_rate, 4),
            context_cost_ratio=round(average_handle_count / 10.0, 4),
            maintenance_cost_ratio=1.0,
            pollution_rate=0.0,
        )

    def close(self) -> None:
        self._store.close()
        self._tempdir.cleanup()


def _build_findings(
    workspace: PublicDatasetWorkspaceSummary,
    long_horizon: PublicDatasetLongHorizonSummary,
    *,
    provider: object,
    provider_configured: bool,
) -> tuple[str, ...]:
    findings: list[str] = []
    if str(provider) != "stub" and not provider_configured:
        findings.append(
            "selected answer provider is not configured, so answer generation "
            "can fall back to deterministic"
        )
    if workspace.candidate_recall_at_20 >= 0.85:
        findings.append("retrieval recall stays above the Phase D baseline")
    else:
        findings.append("retrieval recall falls below the Phase D baseline")
    if workspace.workspace_answer_quality_score >= 0.8:
        findings.append("workspace answers remain high quality on the compiled public cases")
    else:
        findings.append("workspace answer quality needs review on the compiled public cases")
    if long_horizon.average_pus >= 0.3:
        findings.append("long-horizon reuse remains directionally positive on the public fixture")
    else:
        findings.append("long-horizon performance is weak on the public fixture")
    return tuple(findings)


def _report_to_dict(report: PublicDatasetEvaluationReport) -> dict[str, object]:
    return {
        "dataset_name": report.dataset_name,
        "source_path": report.source_path,
        "fixture_name": report.fixture_name,
        "fixture_hash": report.fixture_hash,
        "object_count": report.object_count,
        "retrieval_case_count": report.retrieval_case_count,
        "answer_case_count": report.answer_case_count,
        "long_horizon_sequence_count": report.long_horizon_sequence_count,
        "answer_provider": report.answer_provider,
        "answer_model": report.answer_model,
        "answer_provider_configured": report.answer_provider_configured,
        "long_horizon_strategy": report.long_horizon_strategy,
        "workspace": {
            "case_count": report.workspace.case_count,
            "answer_case_count": report.workspace.answer_case_count,
            "keyword_case_count": report.workspace.keyword_case_count,
            "time_window_case_count": report.workspace.time_window_case_count,
            "vector_case_count": report.workspace.vector_case_count,
            "candidate_recall_at_20": report.workspace.candidate_recall_at_20,
            "workspace_gold_fact_coverage": report.workspace.workspace_gold_fact_coverage,
            "workspace_answer_quality_score": report.workspace.workspace_answer_quality_score,
            "workspace_task_success_rate": report.workspace.workspace_task_success_rate,
            "median_token_cost_ratio": report.workspace.median_token_cost_ratio,
        },
        "long_horizon": {
            "sequence_count": report.long_horizon.sequence_count,
            "average_task_success_rate": report.long_horizon.average_task_success_rate,
            "average_gold_fact_coverage": report.long_horizon.average_gold_fact_coverage,
            "average_reuse_rate": report.long_horizon.average_reuse_rate,
            "average_context_cost_ratio": report.long_horizon.average_context_cost_ratio,
            "average_maintenance_cost_ratio": report.long_horizon.average_maintenance_cost_ratio,
            "average_pollution_rate": report.long_horizon.average_pollution_rate,
            "average_pus": report.long_horizon.average_pus,
        },
        "findings": list(report.findings),
    }


def _coverage(actual_ids: tuple[str, ...], gold_ids: tuple[str, ...]) -> float:
    if not gold_ids:
        return 0.0
    return round(len(set(actual_ids).intersection(gold_ids)) / float(len(gold_ids)), 4)


def _empty_answer_score() -> AnswerScore:
    return AnswerScore(
        task_completion_score=0.0,
        constraint_satisfaction=0.0,
        gold_fact_coverage=0.0,
        answer_faithfulness=0.0,
        answer_quality_score=0.0,
        task_success=False,
    )


def _has_mode(run: RetrievalBenchmarkRun, mode_value: str) -> bool:
    return any(mode.value == mode_value for mode in run.query_modes)


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _long_horizon_strategy(strategy_name: str) -> MindStrategy:
    normalized = strategy_name.strip().lower()
    if normalized == "fixed":
        return FixedRuleMindStrategy()
    if normalized == "optimized":
        return OptimizedMindStrategy()
    if normalized in {"public-dataset", "public_dataset", "public"}:
        return PublicDatasetMindStrategy()
    raise ValueError(
        "unsupported long-horizon strategy "
        f"'{strategy_name}'; expected fixed, optimized, or public-dataset"
    )