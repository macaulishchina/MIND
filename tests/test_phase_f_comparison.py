from __future__ import annotations

import pytest

from mind.eval import evaluate_benchmark_baseline_run_comparison


@pytest.mark.parametrize("family", ["cross_episode_pair", "episode_chain"])
@pytest.mark.parametrize("run_id", [1, 2, 3])
def test_benchmark_comparison_beats_no_memory_baseline_per_family_run(
    family: str,
    run_id: int,
) -> None:
    interval = evaluate_benchmark_baseline_run_comparison(
        baseline_system_id="no_memory",
        families=(family,),
        run_id=run_id,
    )

    assert interval.sample_count == 1
    assert interval.mean_diff >= 0.10
    assert interval.ci_lower > 0.0


@pytest.mark.parametrize("family", ["cross_episode_pair", "episode_chain"])
@pytest.mark.parametrize("run_id", [1, 2, 3])
def test_benchmark_comparison_beats_fixed_summary_memory_baseline_per_family_run(
    family: str,
    run_id: int,
) -> None:
    interval = evaluate_benchmark_baseline_run_comparison(
        baseline_system_id="fixed_summary_memory",
        families=(family,),
        run_id=run_id,
    )

    assert interval.sample_count == 1
    assert interval.mean_diff >= 0.05
    assert interval.ci_lower > 0.0


@pytest.mark.parametrize("family", ["cross_episode_pair", "episode_chain"])
@pytest.mark.parametrize("run_id", [1, 2, 3])
def test_benchmark_comparison_matches_plain_rag_floor_per_family_run(
    family: str,
    run_id: int,
) -> None:
    interval = evaluate_benchmark_baseline_run_comparison(
        baseline_system_id="plain_rag",
        families=(family,),
        run_id=run_id,
    )

    assert interval.sample_count == 1
    assert interval.mean_diff >= -0.02
