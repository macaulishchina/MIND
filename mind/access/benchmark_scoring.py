"""AccessDepthBench scoring, aggregation, and comparison helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mind.fixtures.access_depth_bench import AccessDepthBenchCase

    from .benchmark import (
        AccessBenchmarkRun,
        AccessFrontierComparison,
        AccessGeneratedAnswer,
        AccessModeFamilyAggregate,
    )
    from .contracts import AccessTaskFamily


def task_completion_score(
    case: AccessDepthBenchCase,
    answer: AccessGeneratedAnswer,
) -> float:
    if not case.required_fragments:
        return 0.0
    return round(len(answer.matched_fragments) / float(len(case.required_fragments)), 4)


def constraint_satisfaction(
    case: AccessDepthBenchCase,
    answer: AccessGeneratedAnswer,
) -> float:
    if not case.hard_constraints:
        return 1.0
    satisfied = sum(
        satisfies_constraint(case, answer, constraint) for constraint in case.hard_constraints
    )
    return round(satisfied / float(len(case.hard_constraints)), 4)


def satisfies_constraint(
    case: AccessDepthBenchCase,
    answer: AccessGeneratedAnswer,
    constraint: str,
) -> bool:
    normalized_answer = normalize(answer.text)
    if constraint == "must answer with only success or failure":
        return normalized_answer in {"success", "failure"}
    if constraint == "must include the task result":
        return "success" in normalized_answer or "failure" in normalized_answer
    if constraint == "must include the latest episode summary":
        return (
            len(case.required_fragments) >= 2
            and normalize(case.required_fragments[1]) in normalized_answer
        )
    if constraint == "must identify whether the episode succeeded or failed":
        return "success" in normalized_answer or "failure" in normalized_answer
    if constraint == "must include tool usage when present":
        required_tool_fragments = [
            fragment for fragment in case.required_fragments if "lookup-result-" in fragment
        ]
        if not required_tool_fragments:
            return True
        return any(
            normalize(fragment) in normalized_answer for fragment in required_tool_fragments
        )
    if constraint == "must include the failure or revalidation signal when present":
        if len(case.required_fragments) < 3:
            return True
        return normalize(case.required_fragments[-1]) in normalized_answer
    if constraint.startswith("must stay within "):
        tokens = [part for part in constraint.split() if part.isdigit()]
        if not tokens:
            return False
        return token_count(answer.text) <= int(tokens[0])
    return False


def coverage(actual_ids: tuple[str, ...], gold_ids: tuple[str, ...]) -> float:
    if not gold_ids:
        return 0.0
    return round(len(set(actual_ids).intersection(gold_ids)) / float(len(gold_ids)), 4)


def faithfulness(actual_ids: tuple[str, ...], gold_ids: tuple[str, ...]) -> float:
    if not actual_ids:
        return 0.0
    return round(len(set(actual_ids).intersection(gold_ids)) / float(len(set(actual_ids))), 4)


def support_precision(
    support_ids: tuple[str, ...],
    context_object_ids: tuple[str, ...],
) -> float:
    if not context_object_ids:
        return 0.0
    return round(
        len(set(support_ids).intersection(context_object_ids)) / float(len(context_object_ids)),
        4,
    )


def supplement_gold_support_ids(
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


def answer_trace_support(
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


def estimated_latency_ms(
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


def safe_ratio(value: int | float, baseline: int | float) -> float:
    denominator = float(baseline) if baseline else 1.0
    return round(float(value) / denominator, 4)


def token_count(text: str) -> int:
    return len([token for token in text.split() if token])


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def aggregate_runs(runs: list[AccessBenchmarkRun]) -> list[AccessModeFamilyAggregate]:
    from .benchmark import AccessModeFamilyAggregate as _Agg
    from .contracts import AccessMode, AccessTaskFamily

    aggregates: list[_Agg] = []
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
                _Agg(
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


def build_frontier_comparisons(
    aggregates: tuple[AccessModeFamilyAggregate, ...],
) -> list[AccessFrontierComparison]:
    from .benchmark import AccessFrontierComparison as _FC
    from .contracts import AccessMode, AccessTaskFamily

    comparisons: list[_FC] = []
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
            if meets_family_floor(task_family, aggregate)
        ]
        family_best = max(
            eligible_candidates or fixed_candidates,
            key=lambda aggregate: (
                aggregate.cost_efficiency_score,
                aggregate.answer_quality_score,
            ),
        )
        comparisons.append(
            _FC(
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


def meets_family_floor(
    task_family: AccessTaskFamily,
    aggregate: AccessModeFamilyAggregate,
) -> bool:
    from .contracts import AccessMode
    from .contracts import AccessTaskFamily as _ATF

    if task_family is _ATF.SPEED_SENSITIVE:
        return (
            aggregate.requested_mode is AccessMode.FLASH
            and aggregate.time_budget_hit_rate >= 0.95
            and aggregate.constraint_satisfaction >= 0.95
        )
    if task_family is _ATF.BALANCED:
        return (
            aggregate.requested_mode is AccessMode.RECALL
            and aggregate.answer_quality_score >= 0.75
            and aggregate.memory_use_score >= 0.65
        )
    if aggregate.requested_mode is AccessMode.RECONSTRUCT:
        return aggregate.answer_faithfulness >= 0.95 and aggregate.gold_fact_coverage >= 0.90
    if aggregate.requested_mode is AccessMode.REFLECTIVE_ACCESS:
        return (
            aggregate.answer_faithfulness >= 0.97
            and aggregate.gold_fact_coverage >= 0.92
            and aggregate.constraint_satisfaction >= 0.98
        )
    return False
