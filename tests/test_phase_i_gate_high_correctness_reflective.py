from __future__ import annotations

from mind.access import AccessMode, AccessTaskFamily
from tests._phase_i_gate_support import benchmark_result


def test_phase_i_reflective_high_correctness_slice_passes_current_thresholds() -> None:
    result = benchmark_result(
        AccessTaskFamily.HIGH_CORRECTNESS,
        requested_modes=(AccessMode.REFLECTIVE_ACCESS,),
    )
    aggregate = next(
        aggregate
        for aggregate in result.mode_family_aggregates
        if aggregate.requested_mode is AccessMode.REFLECTIVE_ACCESS
    )

    assert aggregate.answer_faithfulness >= 0.97
    assert aggregate.gold_fact_coverage >= 0.92
    assert aggregate.constraint_satisfaction >= 0.98
