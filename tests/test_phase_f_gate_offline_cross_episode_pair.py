from __future__ import annotations

import pytest

from mind.eval import evaluate_offline_maintenance_ablation_run
from tests._long_horizon_eval_support import family_sequence_chunks

_CROSS_EPISODE_PAIR_CHUNKS = family_sequence_chunks("cross_episode_pair", chunk_size=5)


@pytest.mark.parametrize(
    ("chunk_name", "sequence_ids"),
    _CROSS_EPISODE_PAIR_CHUNKS,
    ids=[chunk_name for chunk_name, _ in _CROSS_EPISODE_PAIR_CHUNKS],
)
@pytest.mark.parametrize("run_id", [1, 2, 3])
def test_phase_f_offline_ablation_passes_thresholds_for_cross_episode_pair_chunk(
    chunk_name: str,
    sequence_ids: tuple[str, ...],
    run_id: int,
) -> None:
    assert chunk_name
    interval = evaluate_offline_maintenance_ablation_run(
        run_id=run_id,
        families=("cross_episode_pair",),
        sequence_ids=sequence_ids,
    )

    assert interval.sample_count == 1
    assert interval.mean_diff >= 0.03
    assert interval.ci_lower >= 0.03
