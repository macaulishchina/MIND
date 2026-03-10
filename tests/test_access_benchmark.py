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
def _benchmark_result() -> AccessBenchmarkResult:
    return evaluate_access_benchmark()


def test_access_benchmark_runs_all_modes_across_all_cases() -> None:
    result = _benchmark_result()

    assert result.case_count == 60
    assert result.run_count == 300
    assert Counter(run.requested_mode for run in result.runs) == {
        AccessMode.FLASH: 60,
        AccessMode.RECALL: 60,
        AccessMode.RECONSTRUCT: 60,
        AccessMode.REFLECTIVE_ACCESS: 60,
        AccessMode.AUTO: 60,
    }
    assert len(result.mode_family_aggregates) == 15
    assert len(result.frontier_comparisons) == 3


def test_access_benchmark_frontier_comparison_uses_expected_fixed_families(
) -> None:
    result = _benchmark_result()
    comparison_by_family = {
        comparison.task_family: comparison for comparison in result.frontier_comparisons
    }

    assert (
        comparison_by_family[AccessTaskFamily.SPEED_SENSITIVE].family_best_fixed_mode
        is AccessMode.FLASH
    )
    assert (
        comparison_by_family[AccessTaskFamily.BALANCED].family_best_fixed_mode
        is AccessMode.RECALL
    )
    assert comparison_by_family[
        AccessTaskFamily.HIGH_CORRECTNESS
    ].family_best_fixed_mode in {
        AccessMode.RECONSTRUCT,
        AccessMode.REFLECTIVE_ACCESS,
    }


def test_access_benchmark_auto_aggregates_exist_for_all_task_families(
) -> None:
    result = _benchmark_result()
    auto_aggregates = {
        aggregate.task_family: aggregate
        for aggregate in result.mode_family_aggregates
        if aggregate.requested_mode is AccessMode.AUTO
    }

    assert set(auto_aggregates) == {
        AccessTaskFamily.SPEED_SENSITIVE,
        AccessTaskFamily.BALANCED,
        AccessTaskFamily.HIGH_CORRECTNESS,
    }
    assert all(
        0.0 <= aggregate.cost_efficiency_score <= 1.0
        for aggregate in auto_aggregates.values()
    )
    assert all(
        0.0 <= aggregate.answer_quality_score <= 1.0
        for aggregate in auto_aggregates.values()
    )
