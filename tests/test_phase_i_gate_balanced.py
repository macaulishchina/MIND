from __future__ import annotations

from mind.access import AccessMode, AccessTaskFamily
from tests._phase_i_gate_support import benchmark_result


def test_phase_i_recall_balanced_slice_passes_current_thresholds() -> None:
    result = benchmark_result(
        AccessTaskFamily.BALANCED,
        requested_modes=(AccessMode.RECALL,),
    )
    aggregate = next(
        aggregate
        for aggregate in result.mode_family_aggregates
        if aggregate.requested_mode is AccessMode.RECALL
    )

    assert aggregate.answer_quality_score >= 0.75
    assert aggregate.memory_use_score >= 0.65


def test_phase_i_balanced_frontier_slice_avoids_regressions() -> None:
    comparison = benchmark_result(
        AccessTaskFamily.BALANCED,
        requested_modes=(AccessMode.RECALL, AccessMode.AUTO),
    ).frontier_comparisons[0]

    assert comparison.auto_aqs_drop <= 0.02
    assert (
        comparison.auto_cost_efficiency_score
        >= comparison.family_best_fixed_cost_efficiency_score
    )
