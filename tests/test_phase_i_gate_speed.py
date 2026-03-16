from __future__ import annotations

from mind.access import AccessMode, AccessTaskFamily
from tests._phase_i_gate_support import benchmark_result


def test_phase_i_flash_speed_slice_passes_current_thresholds() -> None:
    result = benchmark_result(
        AccessTaskFamily.SPEED_SENSITIVE,
        requested_modes=(AccessMode.FLASH,),
    )
    aggregate = next(
        aggregate
        for aggregate in result.mode_family_aggregates
        if aggregate.requested_mode is AccessMode.FLASH
    )

    assert aggregate.time_budget_hit_rate >= 0.95
    assert aggregate.constraint_satisfaction >= 0.85


def test_phase_i_speed_frontier_slice_avoids_regressions() -> None:
    comparison = benchmark_result(
        AccessTaskFamily.SPEED_SENSITIVE,
        requested_modes=(AccessMode.FLASH, AccessMode.AUTO),
    ).frontier_comparisons[0]

    assert comparison.auto_aqs_drop <= 0.02
    assert (
        comparison.auto_cost_efficiency_score
        >= comparison.family_best_fixed_cost_efficiency_score
    )
