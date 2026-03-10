"""Retrieval/workspace smoke evaluation helpers."""

from __future__ import annotations

import statistics
import tempfile
from dataclasses import dataclass
from pathlib import Path

from mind.fixtures.episode_answer_bench import (
    EpisodeAnswerBenchCase,
    build_episode_answer_bench_v1,
)
from mind.fixtures.retrieval_benchmark import (
    RetrievalBenchmarkCase,
    build_canonical_seed_objects,
    build_retrieval_benchmark_v0,
    build_retrieval_benchmark_v1,
)
from mind.kernel.retrieval import build_query_embedding
from mind.kernel.store import MemoryStore, MemoryStoreFactory, SQLiteMemoryStore
from mind.primitives.contracts import (
    PrimitiveExecutionContext,
    PrimitiveOutcome,
    RetrieveQueryMode,
    RetrieveResponse,
)
from mind.primitives.service import PrimitiveService

from .answer_benchmark import (
    AnswerScore,
    answer_from_raw_topk,
    answer_from_workspace,
    score_answer,
)
from .builder import WorkspaceBuilder, WorkspaceBuildError
from .context_protocol import build_raw_topk_context, build_workspace_context


@dataclass(frozen=True)
class RetrievalBenchmarkRun:
    case_id: str
    query_modes: tuple[RetrieveQueryMode, ...]
    outcome: PrimitiveOutcome
    candidate_ids: tuple[str, ...]
    raw_top20_ids: tuple[str, ...]
    workspace_selected_ids: tuple[str, ...]
    candidate_recall_at_20: float
    raw_top20_gold_fact_coverage: float
    workspace_gold_fact_coverage: float
    raw_top20_token_cost: int
    workspace_token_cost: int
    token_cost_ratio: float
    raw_top20_task_completion_score: float
    workspace_task_completion_score: float
    raw_top20_answer_quality_score: float
    workspace_answer_quality_score: float
    raw_top20_task_success: bool
    workspace_task_success: bool
    raw_top20_task_success_proxy: bool
    workspace_task_success_proxy: bool
    workspace_slot_discipline: bool
    workspace_source_ref_coverage: bool


@dataclass(frozen=True)
class WorkspaceSmokeResult:
    smoke_case_count: int
    benchmark_case_count: int
    answer_benchmark_case_count: int
    keyword_smoke_successes: int
    time_window_smoke_successes: int
    vector_smoke_successes: int
    candidate_recall_at_20: float
    workspace_gold_fact_coverage: float
    workspace_slot_discipline_rate: float
    workspace_source_ref_coverage: float
    median_token_cost_ratio: float
    raw_top20_task_success_rate: float
    workspace_task_success_rate: float
    task_success_drop_pp: float
    raw_top20_answer_quality_score: float
    workspace_answer_quality_score: float
    raw_top20_task_success_proxy_rate: float
    workspace_task_success_proxy_rate: float
    task_success_proxy_drop_pp: float
    d5_measured: bool
    runs: tuple[RetrievalBenchmarkRun, ...]

    @property
    def d1_pass(self) -> bool:
        return (
            self.keyword_smoke_successes > 0
            and self.time_window_smoke_successes > 0
            and self.vector_smoke_successes > 0
        )

    @property
    def d2_pass(self) -> bool:
        return self.candidate_recall_at_20 >= 0.85

    @property
    def d3_pass(self) -> bool:
        return self.workspace_gold_fact_coverage >= 0.80

    @property
    def d4_pass(self) -> bool:
        return (
            self.workspace_slot_discipline_rate == 1.0
            and self.workspace_source_ref_coverage == 1.0
        )

    @property
    def d5_pass(self) -> bool:
        return (
            self.d5_measured
            and self.median_token_cost_ratio <= 0.60
            and self.task_success_drop_pp <= 5.0
        )

    @property
    def workspace_smoke_pass(self) -> bool:
        return self.d1_pass and self.d2_pass and self.d3_pass and self.d4_pass and self.d5_pass


def evaluate_workspace_smoke(
    db_path: str | Path | None = None,
    store_factory: MemoryStoreFactory | None = None,
) -> WorkspaceSmokeResult:
    smoke_cases = build_retrieval_benchmark_v0()
    benchmark_cases = build_retrieval_benchmark_v1()
    answer_cases = {case.case_id: case for case in build_episode_answer_bench_v1()}
    seed_objects = build_canonical_seed_objects()

    def default_store_factory(store_path: Path) -> SQLiteMemoryStore:
        return SQLiteMemoryStore(store_path)

    def run(store_path: Path, active_store_factory: MemoryStoreFactory) -> WorkspaceSmokeResult:
        with active_store_factory(store_path) as store:
            store.insert_objects(seed_objects)
            service = PrimitiveService(store, query_embedder=build_query_embedding)
            builder = WorkspaceBuilder(store)
            smoke_runs = [
                _evaluate_case(
                    case=case,
                    answer_case=answer_cases.get(case.case_id),
                    service=service,
                    builder=builder,
                    store=store,
                )
                for case in smoke_cases
            ]
            runs = [
                _evaluate_case(
                    case=case,
                    answer_case=answer_cases[case.case_id],
                    service=service,
                    builder=builder,
                    store=store,
                )
                for case in benchmark_cases
            ]

        raw_top20_success_rate = sum(run.raw_top20_task_success for run in runs) / float(len(runs))
        workspace_success_rate = sum(run.workspace_task_success for run in runs) / float(len(runs))
        raw_top20_proxy_rate = sum(
            run.raw_top20_task_success_proxy for run in runs
        ) / float(len(runs))
        workspace_proxy_rate = sum(
            run.workspace_task_success_proxy for run in runs
        ) / float(len(runs))
        return WorkspaceSmokeResult(
            smoke_case_count=len(smoke_cases),
            benchmark_case_count=len(benchmark_cases),
            answer_benchmark_case_count=len(answer_cases),
            keyword_smoke_successes=sum(
                _mode_success(run, RetrieveQueryMode.KEYWORD) for run in smoke_runs
            ),
            time_window_smoke_successes=sum(
                _mode_success(run, RetrieveQueryMode.TIME_WINDOW) for run in smoke_runs
            ),
            vector_smoke_successes=sum(
                _mode_success(run, RetrieveQueryMode.VECTOR) for run in smoke_runs
            ),
            candidate_recall_at_20=round(
                sum(run.candidate_recall_at_20 for run in runs) / float(len(runs)),
                4,
            ),
            workspace_gold_fact_coverage=round(
                sum(run.workspace_gold_fact_coverage for run in runs) / float(len(runs)),
                4,
            ),
            workspace_slot_discipline_rate=round(
                sum(run.workspace_slot_discipline for run in runs) / float(len(runs)),
                4,
            ),
            workspace_source_ref_coverage=round(
                sum(run.workspace_source_ref_coverage for run in runs) / float(len(runs)),
                4,
            ),
            median_token_cost_ratio=round(
                float(statistics.median(run.token_cost_ratio for run in runs)),
                4,
            ),
            raw_top20_task_success_rate=round(raw_top20_success_rate, 4),
            workspace_task_success_rate=round(workspace_success_rate, 4),
            task_success_drop_pp=round(
                (raw_top20_success_rate - workspace_success_rate) * 100.0,
                4,
            ),
            raw_top20_answer_quality_score=round(
                sum(run.raw_top20_answer_quality_score for run in runs) / float(len(runs)),
                4,
            ),
            workspace_answer_quality_score=round(
                sum(run.workspace_answer_quality_score for run in runs) / float(len(runs)),
                4,
            ),
            raw_top20_task_success_proxy_rate=round(raw_top20_proxy_rate, 4),
            workspace_task_success_proxy_rate=round(workspace_proxy_rate, 4),
            task_success_proxy_drop_pp=round(
                (raw_top20_proxy_rate - workspace_proxy_rate) * 100.0,
                4,
            ),
            d5_measured=True,
            runs=tuple(runs),
        )

    active_factory = store_factory or default_store_factory
    if db_path is not None:
        return run(Path(db_path), active_factory)

    with tempfile.TemporaryDirectory() as tmpdir:
        return run(Path(tmpdir) / "workspace_smoke.sqlite3", active_factory)


def assert_workspace_smoke(result: WorkspaceSmokeResult) -> None:
    if not result.d1_pass:
        raise RuntimeError(
            "D-1 failed: retrieval mode coverage "
            f"(keyword={result.keyword_smoke_successes}, "
            f"time_window={result.time_window_smoke_successes}, "
            f"vector={result.vector_smoke_successes})"
        )
    if not result.d2_pass:
        raise RuntimeError(
            "D-2 failed: candidate recall@20 "
            f"({result.candidate_recall_at_20:.2f})"
        )
    if not result.d3_pass:
        raise RuntimeError(
            "D-3 failed: workspace gold-fact coverage "
            f"({result.workspace_gold_fact_coverage:.2f})"
        )
    if not result.d4_pass:
        raise RuntimeError(
            "D-4 failed: workspace discipline "
            f"(slot_rate={result.workspace_slot_discipline_rate:.2f}, "
            f"source_ref_rate={result.workspace_source_ref_coverage:.2f})"
        )
    if not result.d5_pass:
        raise RuntimeError(
            "D-5 failed: raw-top20 benchmark "
            f"(median_token_cost_ratio={result.median_token_cost_ratio:.2f}, "
            f"task_success_drop_pp={result.task_success_drop_pp:.2f})"
        )


def _evaluate_case(
    *,
    case: RetrievalBenchmarkCase,
    answer_case: EpisodeAnswerBenchCase | None,
    service: PrimitiveService,
    builder: WorkspaceBuilder,
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
            actor="workspace_smoke",
            budget_scope_id=f"workspace::{case.case_id}",
        ),
    )

    response = (
        RetrieveResponse.model_validate(result.response)
        if result.outcome is PrimitiveOutcome.SUCCESS and result.response is not None
        else None
    )
    candidate_ids = tuple(response.candidate_ids if response is not None else ())
    raw_top20_ids = candidate_ids[:20]
    candidate_recall = _recall_at_k(candidate_ids, case.gold_candidate_ids, k=20)
    raw_top20_gold_fact_coverage = _coverage(raw_top20_ids, case.gold_fact_ids)
    raw_context = build_raw_topk_context(store, raw_top20_ids)
    raw_top20_token_cost = raw_context.token_count
    raw_answer_score = (
        score_answer(answer_case, answer_from_raw_topk(answer_case, raw_context))
        if answer_case is not None
        else score_answer_placeholder()
    )
    raw_top20_task_success_proxy = _task_success_proxy(raw_top20_gold_fact_coverage)

    workspace_coverage = 0.0
    workspace_selected_ids: tuple[str, ...] = ()
    workspace_token_cost = raw_top20_token_cost
    token_cost_ratio = 1.0 if raw_top20_token_cost > 0 else 0.0
    workspace_answer_score = score_answer_placeholder()
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
                workspace_id=f"workspace-{case.case_id}",
            )
        except WorkspaceBuildError:
            workspace_result = None
        if workspace_result is not None:
            workspace = workspace_result.workspace
            slots = workspace["metadata"]["slots"]
            workspace_selected_ids = workspace_result.selected_ids
            workspace_coverage = _coverage(workspace_selected_ids, case.gold_fact_ids)
            workspace_context = build_workspace_context(workspace)
            workspace_token_cost = workspace_context.token_count
            if answer_case is not None:
                workspace_answer_score = score_answer(
                    answer_case,
                    answer_from_workspace(answer_case, workspace_context),
                )
            token_cost_ratio = _safe_ratio(workspace_token_cost, raw_top20_token_cost)
            workspace_task_success_proxy = _task_success_proxy(workspace_coverage)
            slot_discipline = len(slots) <= case.slot_limit
            source_ref_coverage = all(bool(slot["source_refs"]) for slot in slots)

    return RetrievalBenchmarkRun(
        case_id=case.case_id,
        query_modes=case.query_modes,
        outcome=result.outcome,
        candidate_ids=candidate_ids,
        raw_top20_ids=raw_top20_ids,
        workspace_selected_ids=workspace_selected_ids,
        candidate_recall_at_20=candidate_recall,
        raw_top20_gold_fact_coverage=raw_top20_gold_fact_coverage,
        workspace_gold_fact_coverage=workspace_coverage,
        raw_top20_token_cost=raw_top20_token_cost,
        workspace_token_cost=workspace_token_cost,
        token_cost_ratio=token_cost_ratio,
        raw_top20_task_completion_score=raw_answer_score.task_completion_score,
        workspace_task_completion_score=workspace_answer_score.task_completion_score,
        raw_top20_answer_quality_score=raw_answer_score.answer_quality_score,
        workspace_answer_quality_score=workspace_answer_score.answer_quality_score,
        raw_top20_task_success=raw_answer_score.task_success,
        workspace_task_success=workspace_answer_score.task_success,
        raw_top20_task_success_proxy=raw_top20_task_success_proxy,
        workspace_task_success_proxy=workspace_task_success_proxy,
        workspace_slot_discipline=slot_discipline,
        workspace_source_ref_coverage=source_ref_coverage,
    )


def _recall_at_k(candidate_ids: tuple[str, ...], gold_ids: tuple[str, ...], *, k: int) -> float:
    return _coverage(candidate_ids[:k], gold_ids)


def _coverage(candidate_ids: tuple[str, ...], gold_ids: tuple[str, ...]) -> float:
    if not gold_ids:
        return 0.0
    gold_set = set(gold_ids)
    hit_count = len(gold_set.intersection(candidate_ids))
    return hit_count / float(len(gold_set))


def _task_success_proxy(gold_fact_coverage: float) -> bool:
    return gold_fact_coverage == 1.0


def score_answer_placeholder() -> AnswerScore:
    return AnswerScore(
        task_completion_score=0.0,
        constraint_satisfaction=0.0,
        gold_fact_coverage=0.0,
        answer_faithfulness=0.0,
        answer_quality_score=0.0,
        task_success=False,
    )


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0 if numerator == 0 else 1.0
    return round(numerator / float(denominator), 4)


def _mode_success(run: RetrievalBenchmarkRun, mode: RetrieveQueryMode) -> bool:
    return (
        mode in run.query_modes
        and run.outcome is PrimitiveOutcome.SUCCESS
        and run.candidate_recall_at_20 > 0
    )
