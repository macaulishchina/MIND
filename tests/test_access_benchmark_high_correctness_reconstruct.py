from __future__ import annotations

from collections import Counter
from functools import lru_cache

import pytest

from mind.access import (
    AccessBenchmarkResult,
    AccessMode,
    AccessTaskFamily,
    evaluate_access_benchmark,
)
from tests._access_benchmark_support import episode_chunks

_EPISODE_CHUNKS = episode_chunks(chunk_size=10)


@lru_cache(maxsize=2)
def _frontier_result(episode_ids: tuple[str, ...]) -> AccessBenchmarkResult:
    return evaluate_access_benchmark(
        task_families=(AccessTaskFamily.HIGH_CORRECTNESS,),
        requested_modes=(AccessMode.RECONSTRUCT, AccessMode.AUTO),
        episode_ids=episode_ids,
    )


@pytest.mark.parametrize(
    ("chunk_name", "episode_ids"),
    _EPISODE_CHUNKS,
    ids=[chunk_name for chunk_name, _ in _EPISODE_CHUNKS],
)
def test_access_benchmark_high_correctness_reconstruct_frontier_slice_avoids_regressions(
    chunk_name: str,
    episode_ids: tuple[str, ...],
) -> None:
    assert chunk_name
    result = _frontier_result(episode_ids)

    assert result.case_count == 10
    assert result.run_count == 20
    assert Counter(run.requested_mode for run in result.runs) == {
        AccessMode.RECONSTRUCT: 10,
        AccessMode.AUTO: 10,
    }
    assert len(result.mode_family_aggregates) == 2
    assert len(result.frontier_comparisons) == 1
    comparison = result.frontier_comparisons[0]
    assert comparison.task_family is AccessTaskFamily.HIGH_CORRECTNESS
    assert comparison.family_best_fixed_mode is AccessMode.RECONSTRUCT
    assert comparison.auto_aqs_drop <= 0.02
    assert (
        comparison.auto_cost_efficiency_score
        >= comparison.family_best_fixed_cost_efficiency_score
    )
