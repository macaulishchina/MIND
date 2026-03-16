from __future__ import annotations

import pytest

from mind.access import AccessMode, AccessTaskFamily
from tests._access_benchmark_support import episode_chunks
from tests._phase_i_gate_support import benchmark_result

_EPISODE_CHUNKS = episode_chunks(chunk_size=10)


@pytest.mark.parametrize(
    ("chunk_name", "episode_ids"),
    _EPISODE_CHUNKS,
    ids=[chunk_name for chunk_name, _ in _EPISODE_CHUNKS],
)
def test_phase_i_high_correctness_reflective_frontier_slice_avoids_regressions(
    chunk_name: str,
    episode_ids: tuple[str, ...],
) -> None:
    assert chunk_name
    comparison = benchmark_result(
        AccessTaskFamily.HIGH_CORRECTNESS,
        requested_modes=(AccessMode.REFLECTIVE_ACCESS, AccessMode.AUTO),
        episode_ids=episode_ids,
    ).frontier_comparisons[0]

    assert comparison.family_best_fixed_mode is AccessMode.REFLECTIVE_ACCESS
    assert comparison.auto_aqs_drop <= 0.02
    assert (
        comparison.auto_cost_efficiency_score
        >= comparison.family_best_fixed_cost_efficiency_score
    )
