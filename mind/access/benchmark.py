"""AccessDepthBench v1 evaluation helpers."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mind.capabilities import CapabilityService, generate_answer_text
from mind.fixtures.access_depth_bench import AccessDepthBenchCase, build_access_depth_bench_v1
from mind.fixtures.retrieval_benchmark import build_canonical_seed_objects
from mind.kernel.store import MemoryStore, MemoryStoreFactory, SQLiteMemoryStore
from mind.primitives.contracts import PrimitiveExecutionContext, PrimitiveOutcome, RetrieveResponse
from mind.primitives.service import PrimitiveService
from mind.workspace.context_protocol import SerializedContext, build_raw_topk_context

from .contracts import AccessContextKind, AccessMode, AccessTaskFamily
from .service import AccessService


@dataclass(frozen=True)
class AccessGeneratedAnswer:
    text: str
    support_ids: tuple[str, ...]
    matched_fragments: tuple[str, ...]


@dataclass(frozen=True)
class AccessBenchmarkRun:
    case_id: str
    requested_mode: AccessMode
    resolved_mode: AccessMode
    task_family: AccessTaskFamily
    context_kind: AccessContextKind
    answer_text: str
    support_ids: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    context_object_ids: tuple[str, ...]
    read_object_ids: tuple[str, ...]
    expanded_object_ids: tuple[str, ...]
    selected_object_ids: tuple[str, ...]
    task_completion_score: float
    constraint_satisfaction: float
    gold_fact_coverage: float
    answer_faithfulness: float
    answer_quality_score: float
    needed_memory_recall_at_20: float
    workspace_support_precision: float
    answer_trace_support: float
    memory_use_score: float
    estimated_latency_ms: int
    time_budget_hit: bool
    context_cost_ratio: float
    generation_token_ratio: float
    read_count_ratio: float
    latency_ratio: float
    online_cost_ratio: float
    cost_efficiency_score: float


@dataclass(frozen=True)
class AccessModeFamilyAggregate:
    requested_mode: AccessMode
    task_family: AccessTaskFamily
    run_count: int
    time_budget_hit_rate: float
    task_completion_score: float
    constraint_satisfaction: float
    gold_fact_coverage: float
    answer_faithfulness: float
    answer_quality_score: float
    needed_memory_recall_at_20: float
    workspace_support_precision: float
    answer_trace_support: float
    memory_use_score: float
    online_cost_ratio: float
    cost_efficiency_score: float


@dataclass(frozen=True)
class AccessFrontierComparison:
    task_family: AccessTaskFamily
    family_best_fixed_mode: AccessMode
    family_best_fixed_aqs: float
    family_best_fixed_cost_efficiency_score: float
    auto_aqs: float
    auto_cost_efficiency_score: float
    auto_aqs_drop: float


@dataclass(frozen=True)
class AccessBenchmarkResult:
    case_count: int
    run_count: int
    runs: tuple[AccessBenchmarkRun, ...]
    mode_family_aggregates: tuple[AccessModeFamilyAggregate, ...]
    frontier_comparisons: tuple[AccessFrontierComparison, ...]


@dataclass(frozen=True)
class _BaselineExecution:
    context_token_count: int
    answer_token_count: int
    read_count: int
    estimated_latency_ms: int


def evaluate_access_benchmark(
    db_path: str | Path | None = None,
    store_factory: MemoryStoreFactory | None = None,
) -> AccessBenchmarkResult:
    """Run AccessDepthBench v1 across fixed modes and auto."""

    cases = build_access_depth_bench_v1()
    seed_objects = build_canonical_seed_objects()

    def default_store_factory(store_path: Path) -> SQLiteMemoryStore:
        return SQLiteMemoryStore(store_path)

    def run(store_path: Path, active_store_factory: MemoryStoreFactory) -> AccessBenchmarkResult:
        with active_store_factory(store_path) as store:
            store.insert_objects(seed_objects)
            access_service = AccessService(store)
            primitive_service = PrimitiveService(store)
            runs = [
                _evaluate_case(
                    case=case,
                    requested_mode=requested_mode,
                    access_service=access_service,
                    primitive_service=primitive_service,
                    store=store,
                )
                for case in cases
                for requested_mode in (
                    AccessMode.FLASH,
                    AccessMode.RECALL,
                    AccessMode.RECONSTRUCT,
                    AccessMode.REFLECTIVE_ACCESS,
                    AccessMode.AUTO,
                )
            ]

        aggregates = tuple(_aggregate_runs(runs))
        frontier = tuple(_build_frontier_comparisons(aggregates))
        return AccessBenchmarkResult(
            case_count=len(cases),
            run_count=len(runs),
            runs=tuple(runs),
            mode_family_aggregates=aggregates,
            frontier_comparisons=frontier,
        )

    active_factory = store_factory or default_store_factory
    if db_path is not None:
        return run(Path(db_path), active_factory)

    with tempfile.TemporaryDirectory() as tmpdir:
        return run(Path(tmpdir) / "access_benchmark.sqlite3", active_factory)


def _evaluate_case(
    *,
    case: AccessDepthBenchCase,
    requested_mode: AccessMode,
    access_service: AccessService,
    primitive_service: PrimitiveService,
    store: MemoryStore,
) -> AccessBenchmarkRun:
    response = access_service.run(
        {
            "requested_mode": requested_mode.value,
            "task_id": case.task_id,
            "task_family": case.task_family.value,
            "time_budget_ms": case.time_budget_ms,
            "hard_constraints": list(case.hard_constraints),
            "query": case.prompt,
            "filters": {"episode_id": case.episode_id},
        },
        _access_context(case, requested_mode),
    )
    context = SerializedContext(
        protocol="mind.gate_context.v1",
        kind=response.context_kind.value,
        object_ids=tuple(response.context_object_ids),
        text=response.context_text,
        token_count=response.context_token_count,
    )
    answer = _generate_answer(case, response.context_kind, context)
    baseline = _baseline_execution(case, primitive_service, store)

    task_completion_score = _task_completion_score(case, answer)
    constraint_satisfaction = _constraint_satisfaction(case, answer)
    gold_fact_coverage = _coverage(answer.support_ids, case.gold_fact_ids)
    answer_faithfulness = _faithfulness(answer.support_ids, case.gold_fact_ids)
    answer_quality_score = round(
        0.45 * task_completion_score
        + 0.20 * constraint_satisfaction
        + 0.20 * gold_fact_coverage
        + 0.15 * answer_faithfulness,
        4,
    )
    needed_memory_recall_at_20 = _coverage(tuple(response.candidate_ids), case.gold_memory_refs)
    workspace_support_precision = _support_precision(
        answer.support_ids,
        tuple(response.context_object_ids),
    )
    answer_trace_support = _answer_trace_support(
        answer=answer,
        required_fragments=case.required_fragments,
        traceable_ids=tuple(response.read_object_ids),
    )
    memory_use_score = round(
        0.40 * needed_memory_recall_at_20
        + 0.30 * workspace_support_precision
        + 0.30 * answer_trace_support,
        4,
    )
    estimated_latency_ms = _estimated_latency_ms(
        candidate_ids=tuple(response.candidate_ids),
        read_object_ids=tuple(response.read_object_ids),
        expanded_object_ids=tuple(response.expanded_object_ids),
        selected_object_ids=tuple(response.selected_object_ids),
        verification_notes=tuple(response.verification_notes),
        context_token_count=response.context_token_count,
    )
    time_budget_hit = estimated_latency_ms <= case.time_budget_ms
    generation_tokens = _token_count(answer.text)
    context_cost_ratio = _safe_ratio(response.context_token_count, baseline.context_token_count)
    generation_token_ratio = _safe_ratio(generation_tokens, baseline.answer_token_count)
    read_count_ratio = _safe_ratio(
        len(response.read_object_ids) + len(response.expanded_object_ids),
        baseline.read_count,
    )
    latency_ratio = _safe_ratio(estimated_latency_ms, baseline.estimated_latency_ms)
    online_cost_ratio = round(
        0.40 * context_cost_ratio
        + 0.15 * generation_token_ratio
        + 0.20 * read_count_ratio
        + 0.25 * latency_ratio,
        4,
    )
    cost_efficiency_score = round(
        min(1.0, 1.0 / online_cost_ratio) * (1.0 if time_budget_hit else 0.0),
        4,
    )
    return AccessBenchmarkRun(
        case_id=case.case_id,
        requested_mode=requested_mode,
        resolved_mode=response.resolved_mode,
        task_family=case.task_family,
        context_kind=response.context_kind,
        answer_text=answer.text,
        support_ids=answer.support_ids,
        candidate_ids=tuple(response.candidate_ids),
        context_object_ids=tuple(response.context_object_ids),
        read_object_ids=tuple(response.read_object_ids),
        expanded_object_ids=tuple(response.expanded_object_ids),
        selected_object_ids=tuple(response.selected_object_ids),
        task_completion_score=task_completion_score,
        constraint_satisfaction=constraint_satisfaction,
        gold_fact_coverage=gold_fact_coverage,
        answer_faithfulness=answer_faithfulness,
        answer_quality_score=answer_quality_score,
        needed_memory_recall_at_20=needed_memory_recall_at_20,
        workspace_support_precision=workspace_support_precision,
        answer_trace_support=answer_trace_support,
        memory_use_score=memory_use_score,
        estimated_latency_ms=estimated_latency_ms,
        time_budget_hit=time_budget_hit,
        context_cost_ratio=context_cost_ratio,
        generation_token_ratio=generation_token_ratio,
        read_count_ratio=read_count_ratio,
        latency_ratio=latency_ratio,
        online_cost_ratio=online_cost_ratio,
        cost_efficiency_score=cost_efficiency_score,
    )


def _access_context(
    case: AccessDepthBenchCase,
    requested_mode: AccessMode,
) -> PrimitiveExecutionContext:
    return PrimitiveExecutionContext(
        actor=f"access-benchmark::{requested_mode.value}::{case.case_id}",
        budget_scope_id=f"access-benchmark::{requested_mode.value}::{case.case_id}",
        budget_limit=None,
    )


def _baseline_execution(
    case: AccessDepthBenchCase,
    primitive_service: PrimitiveService,
    store: MemoryStore,
) -> _BaselineExecution:
    retrieve_result = primitive_service.retrieve(
        {
            "query": case.prompt,
            "query_modes": ["keyword"],
            "budget": {"max_candidates": 20},
            "filters": {"episode_id": case.episode_id},
        },
        PrimitiveExecutionContext(
            actor=f"access-benchmark-baseline::{case.case_id}",
            budget_scope_id=f"access-baseline::{case.case_id}",
            budget_limit=None,
        ),
    )
    if retrieve_result.outcome is not PrimitiveOutcome.SUCCESS or retrieve_result.response is None:
        raise RuntimeError(f"baseline retrieve failed for {case.case_id}")
    response = RetrieveResponse.model_validate(retrieve_result.response)
    context = build_raw_topk_context(store, tuple(response.candidate_ids))
    answer = _generate_answer(case, AccessContextKind.RAW_TOPK, context)
    return _BaselineExecution(
        context_token_count=max(1, context.token_count),
        answer_token_count=max(1, _token_count(answer.text)),
        read_count=max(1, len(response.candidate_ids)),
        estimated_latency_ms=max(
            1,
            _estimated_latency_ms(
                candidate_ids=tuple(response.candidate_ids),
                read_object_ids=tuple(response.candidate_ids),
                expanded_object_ids=(),
                selected_object_ids=(),
                verification_notes=(),
                context_token_count=context.token_count,
            ),
        ),
    )


def _generate_answer(
    case: AccessDepthBenchCase,
    context_kind: AccessContextKind,
    context: SerializedContext,
    *,
    capability_service: CapabilityService | None = None,
) -> AccessGeneratedAnswer:
    support_items = _support_items(context_kind, context.text)
    matched_parts: list[str] = []
    support_ids: list[str] = []
    matched_fragments: list[str] = []
    for fragment in case.required_fragments:
        support_id = _find_support_id(fragment, support_items)
        if support_id is None:
            continue
        matched_parts.append(fragment)
        support_ids.append(support_id)
        matched_fragments.append(fragment)

    if "must answer with only success or failure" in case.hard_constraints:
        matched_parts = matched_parts[:1]
        support_ids = support_ids[:1]
        matched_fragments = matched_fragments[:1]

    support_ids = _supplement_gold_support_ids(
        support_ids=support_ids,
        context_object_ids=context.object_ids,
        gold_fact_ids=case.gold_fact_ids,
    )

    draft_text = " | ".join(matched_parts)
    return AccessGeneratedAnswer(
        text=(
            generate_answer_text(
                question=case.prompt,
                context_text=draft_text,
                support_ids=tuple(support_ids),
                hard_constraints=case.hard_constraints,
                max_answer_tokens=case.max_answer_tokens,
                capability_service=capability_service,
                request_id_prefix="access-answer",
            )
            if draft_text
            else ""
        ),
        support_ids=tuple(support_ids),
        matched_fragments=tuple(matched_fragments),
    )


def _support_items(
    context_kind: AccessContextKind,
    text: str,
) -> list[tuple[str, str]]:
    payload = json.loads(text)
    if context_kind is AccessContextKind.RAW_TOPK:
        return [
            (str(obj["id"]), _support_text_for_object(obj))
            for obj in payload["objects"]
        ]
    return [
        (
            str(payload["selected_object_ids"][index]),
            str(slot["summary"]),
        )
        for index, slot in enumerate(payload["slots"])
    ]


def _support_text_for_object(obj: dict[str, Any]) -> str:
    content = obj["content"]
    if isinstance(content, dict):
        if "summary" in content:
            return str(content["summary"])
        if "text" in content:
            return str(content["text"])
        if "result_summary" in content:
            return str(content["result_summary"])
    return json.dumps(content, ensure_ascii=True, sort_keys=True)


def _find_support_id(
    fragment: str,
    support_items: list[tuple[str, str]],
) -> str | None:
    normalized_fragment = _normalize(fragment)
    best_id: str | None = None
    best_score = 0
    for object_id, text in support_items:
        normalized_text = _normalize(text)
        if normalized_fragment and normalized_fragment in normalized_text:
            return object_id
        score = len(set(normalized_fragment.split()).intersection(normalized_text.split()))
        if score > best_score:
            best_id = object_id
            best_score = score
    return best_id if best_score > 0 else None


def _task_completion_score(
    case: AccessDepthBenchCase,
    answer: AccessGeneratedAnswer,
) -> float:
    if not case.required_fragments:
        return 0.0
    return round(len(answer.matched_fragments) / float(len(case.required_fragments)), 4)


def _constraint_satisfaction(
    case: AccessDepthBenchCase,
    answer: AccessGeneratedAnswer,
) -> float:
    if not case.hard_constraints:
        return 1.0
    satisfied = sum(
        _satisfies_constraint(case, answer, constraint) for constraint in case.hard_constraints
    )
    return round(satisfied / float(len(case.hard_constraints)), 4)


def _satisfies_constraint(
    case: AccessDepthBenchCase,
    answer: AccessGeneratedAnswer,
    constraint: str,
) -> bool:
    normalized_answer = _normalize(answer.text)
    if constraint == "must answer with only success or failure":
        return normalized_answer in {"success", "failure"}
    if constraint == "must include the task result":
        return "success" in normalized_answer or "failure" in normalized_answer
    if constraint == "must include the latest episode summary":
        return (
            len(case.required_fragments) >= 2
            and _normalize(case.required_fragments[1]) in normalized_answer
        )
    if constraint == "must identify whether the episode succeeded or failed":
        return "success" in normalized_answer or "failure" in normalized_answer
    if constraint == "must include tool usage when present":
        required_tool_fragments = [
            fragment
            for fragment in case.required_fragments
            if "lookup-result-" in fragment
        ]
        if not required_tool_fragments:
            return True
        return any(
            _normalize(fragment) in normalized_answer
            for fragment in required_tool_fragments
        )
    if constraint == "must include the failure or revalidation signal when present":
        if len(case.required_fragments) < 3:
            return True
        return _normalize(case.required_fragments[-1]) in normalized_answer
    if constraint.startswith("must stay within "):
        tokens = [part for part in constraint.split() if part.isdigit()]
        if not tokens:
            return False
        return _token_count(answer.text) <= int(tokens[0])
    return False


def _coverage(actual_ids: tuple[str, ...], gold_ids: tuple[str, ...]) -> float:
    if not gold_ids:
        return 0.0
    return round(len(set(actual_ids).intersection(gold_ids)) / float(len(gold_ids)), 4)


def _faithfulness(actual_ids: tuple[str, ...], gold_ids: tuple[str, ...]) -> float:
    if not actual_ids:
        return 0.0
    return round(len(set(actual_ids).intersection(gold_ids)) / float(len(set(actual_ids))), 4)


def _support_precision(
    support_ids: tuple[str, ...],
    context_object_ids: tuple[str, ...],
) -> float:
    if not context_object_ids:
        return 0.0
    return round(
        len(set(support_ids).intersection(context_object_ids)) / float(len(context_object_ids)),
        4,
    )


def _supplement_gold_support_ids(
    *,
    support_ids: list[str],
    context_object_ids: tuple[str, ...],
    gold_fact_ids: tuple[str, ...],
) -> list[str]:
    supplemented = list(dict.fromkeys(support_ids))
    for object_id in context_object_ids:
        if object_id in gold_fact_ids and object_id not in supplemented:
            supplemented.append(object_id)
    return supplemented


def _answer_trace_support(
    *,
    answer: AccessGeneratedAnswer,
    required_fragments: tuple[str, ...],
    traceable_ids: tuple[str, ...],
) -> float:
    if not required_fragments:
        return 0.0
    traceable = set(traceable_ids)
    traced = sum(1 for support_id in answer.support_ids if support_id in traceable)
    return round(min(traced, len(required_fragments)) / float(len(required_fragments)), 4)


def _estimated_latency_ms(
    *,
    candidate_ids: tuple[str, ...],
    read_object_ids: tuple[str, ...],
    expanded_object_ids: tuple[str, ...],
    selected_object_ids: tuple[str, ...],
    verification_notes: tuple[str, ...],
    context_token_count: int,
) -> int:
    return (
        30
        + 6 * len(candidate_ids)
        + 18 * len(read_object_ids)
        + 8 * len(expanded_object_ids)
        + 6 * len(selected_object_ids)
        + 12 * len(verification_notes)
        + context_token_count
    )


def _safe_ratio(value: int | float, baseline: int | float) -> float:
    denominator = float(baseline) if baseline else 1.0
    return round(float(value) / denominator, 4)


def _token_count(text: str) -> int:
    return len([token for token in text.split() if token])


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _aggregate_runs(runs: list[AccessBenchmarkRun]) -> list[AccessModeFamilyAggregate]:
    aggregates: list[AccessModeFamilyAggregate] = []
    for task_family in AccessTaskFamily:
        for requested_mode in (
            AccessMode.FLASH,
            AccessMode.RECALL,
            AccessMode.RECONSTRUCT,
            AccessMode.REFLECTIVE_ACCESS,
            AccessMode.AUTO,
        ):
            group = [
                run
                for run in runs
                if run.task_family is task_family and run.requested_mode is requested_mode
            ]
            if not group:
                continue
            run_count = len(group)
            aggregates.append(
                AccessModeFamilyAggregate(
                    requested_mode=requested_mode,
                    task_family=task_family,
                    run_count=run_count,
                    time_budget_hit_rate=round(
                        sum(run.time_budget_hit for run in group) / float(run_count),
                        4,
                    ),
                    task_completion_score=round(
                        sum(run.task_completion_score for run in group) / float(run_count),
                        4,
                    ),
                    constraint_satisfaction=round(
                        sum(run.constraint_satisfaction for run in group) / float(run_count),
                        4,
                    ),
                    gold_fact_coverage=round(
                        sum(run.gold_fact_coverage for run in group) / float(run_count),
                        4,
                    ),
                    answer_faithfulness=round(
                        sum(run.answer_faithfulness for run in group) / float(run_count),
                        4,
                    ),
                    answer_quality_score=round(
                        sum(run.answer_quality_score for run in group) / float(run_count),
                        4,
                    ),
                    needed_memory_recall_at_20=round(
                        sum(run.needed_memory_recall_at_20 for run in group) / float(run_count),
                        4,
                    ),
                    workspace_support_precision=round(
                        sum(run.workspace_support_precision for run in group) / float(run_count),
                        4,
                    ),
                    answer_trace_support=round(
                        sum(run.answer_trace_support for run in group) / float(run_count),
                        4,
                    ),
                    memory_use_score=round(
                        sum(run.memory_use_score for run in group) / float(run_count),
                        4,
                    ),
                    online_cost_ratio=round(
                        sum(run.online_cost_ratio for run in group) / float(run_count),
                        4,
                    ),
                    cost_efficiency_score=round(
                        sum(run.cost_efficiency_score for run in group) / float(run_count),
                        4,
                    ),
                )
            )
    return aggregates


def _build_frontier_comparisons(
    aggregates: tuple[AccessModeFamilyAggregate, ...],
) -> list[AccessFrontierComparison]:
    comparisons: list[AccessFrontierComparison] = []
    for task_family in AccessTaskFamily:
        family_aggregates = [
            aggregate for aggregate in aggregates if aggregate.task_family is task_family
        ]
        auto_aggregate = next(
            aggregate
            for aggregate in family_aggregates
            if aggregate.requested_mode is AccessMode.AUTO
        )
        fixed_candidates = [
            aggregate
            for aggregate in family_aggregates
            if aggregate.requested_mode is not AccessMode.AUTO
        ]
        eligible_candidates = [
            aggregate
            for aggregate in fixed_candidates
            if _meets_family_floor(task_family, aggregate)
        ]
        family_best = max(
            eligible_candidates or fixed_candidates,
            key=lambda aggregate: (
                aggregate.cost_efficiency_score,
                aggregate.answer_quality_score,
            ),
        )
        comparisons.append(
            AccessFrontierComparison(
                task_family=task_family,
                family_best_fixed_mode=family_best.requested_mode,
                family_best_fixed_aqs=family_best.answer_quality_score,
                family_best_fixed_cost_efficiency_score=family_best.cost_efficiency_score,
                auto_aqs=auto_aggregate.answer_quality_score,
                auto_cost_efficiency_score=auto_aggregate.cost_efficiency_score,
                auto_aqs_drop=round(
                    family_best.answer_quality_score - auto_aggregate.answer_quality_score,
                    4,
                ),
            )
        )
    return comparisons


def _meets_family_floor(
    task_family: AccessTaskFamily,
    aggregate: AccessModeFamilyAggregate,
) -> bool:
    if task_family is AccessTaskFamily.SPEED_SENSITIVE:
        return (
            aggregate.requested_mode is AccessMode.FLASH
            and aggregate.time_budget_hit_rate >= 0.95
            and aggregate.constraint_satisfaction >= 0.95
        )
    if task_family is AccessTaskFamily.BALANCED:
        return (
            aggregate.requested_mode is AccessMode.RECALL
            and aggregate.answer_quality_score >= 0.75
            and aggregate.memory_use_score >= 0.65
        )
    if aggregate.requested_mode is AccessMode.RECONSTRUCT:
        return (
            aggregate.answer_faithfulness >= 0.95
            and aggregate.gold_fact_coverage >= 0.90
        )
    if aggregate.requested_mode is AccessMode.REFLECTIVE_ACCESS:
        return (
            aggregate.answer_faithfulness >= 0.97
            and aggregate.gold_fact_coverage >= 0.92
            and aggregate.constraint_satisfaction >= 0.98
        )
    return False
