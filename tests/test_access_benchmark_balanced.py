from __future__ import annotations

from collections import Counter
from functools import lru_cache

from mind.access import (
    AccessBenchmarkResult,
    AccessMode,
    AccessTaskFamily,
    evaluate_access_benchmark,
)


@lru_cache(maxsize=1)
def _recall_result() -> AccessBenchmarkResult:
    return evaluate_access_benchmark(
        task_families=(AccessTaskFamily.BALANCED,),
        requested_modes=(AccessMode.RECALL,),
    )


@lru_cache(maxsize=1)
def _frontier_result() -> AccessBenchmarkResult:
    return evaluate_access_benchmark(
        task_families=(AccessTaskFamily.BALANCED,),
        requested_modes=(AccessMode.RECALL, AccessMode.AUTO),
    )


def test_access_benchmark_balanced_family_recall_slice_hits_current_floor() -> None:
    result = _recall_result()

    assert result.case_count == 20
    assert result.run_count == 20
    assert Counter(run.requested_mode for run in result.runs) == {AccessMode.RECALL: 20}
    assert len(result.mode_family_aggregates) == 1
    aggregate = result.mode_family_aggregates[0]
    assert aggregate.requested_mode is AccessMode.RECALL
    assert aggregate.task_family is AccessTaskFamily.BALANCED
    assert aggregate.answer_quality_score >= 0.75
    assert aggregate.memory_use_score >= 0.65


def test_access_benchmark_balanced_family_frontier_slice_avoids_regressions() -> None:
    result = _frontier_result()

    assert result.case_count == 20
    assert result.run_count == 40
    assert Counter(run.requested_mode for run in result.runs) == {
        AccessMode.RECALL: 20,
        AccessMode.AUTO: 20,
    }
    assert len(result.mode_family_aggregates) == 2
    assert len(result.frontier_comparisons) == 1
    comparison = result.frontier_comparisons[0]
    assert comparison.task_family is AccessTaskFamily.BALANCED
    assert comparison.family_best_fixed_mode is AccessMode.RECALL
    assert comparison.auto_aqs_drop <= 0.02
    assert (
        comparison.auto_cost_efficiency_score
        >= comparison.family_best_fixed_cost_efficiency_score
    )
