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

from .benchmark_scoring import (
    aggregate_runs as _aggregate_runs,
)
from .benchmark_scoring import (
    answer_trace_support as _answer_trace_support,
)
from .benchmark_scoring import (
    build_frontier_comparisons as _build_frontier_comparisons,
)
from .benchmark_scoring import (
    constraint_satisfaction as _constraint_satisfaction,
)
from .benchmark_scoring import (
    coverage as _coverage,
)
from .benchmark_scoring import (
    estimated_latency_ms as _estimated_latency_ms,
)
from .benchmark_scoring import (
    faithfulness as _faithfulness,
)
from .benchmark_scoring import (
    normalize as _normalize,
)
from .benchmark_scoring import (
    safe_ratio as _safe_ratio,
)
from .benchmark_scoring import (
    supplement_gold_support_ids as _supplement_gold_support_ids,
)
from .benchmark_scoring import (
    support_precision as _support_precision,
)
from .benchmark_scoring import (
    task_completion_score as _task_completion_score,
)
from .benchmark_scoring import (
    token_count as _token_count,
)
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
            runs: list[AccessBenchmarkRun] = []
            for case in cases:
                baseline = _baseline_execution(case, primitive_service, store)
                for requested_mode in (
                    AccessMode.FLASH,
                    AccessMode.RECALL,
                    AccessMode.RECONSTRUCT,
                    AccessMode.REFLECTIVE_ACCESS,
                    AccessMode.AUTO,
                ):
                    runs.append(
                        _evaluate_case(
                            case=case,
                            requested_mode=requested_mode,
                            access_service=access_service,
                            baseline=baseline,
                        )
                    )

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
    baseline: _BaselineExecution,
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
        return [(str(obj["id"]), _support_text_for_object(obj)) for obj in payload["objects"]]
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

