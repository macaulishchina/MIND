from __future__ import annotations

import pytest

from mind.eval import evaluate_offline_maintenance_ablation_run
from tests._long_horizon_eval_support import family_sequence_chunks

_EPISODE_CHAIN_CHUNKS = family_sequence_chunks("episode_chain", chunk_size=5)


@pytest.mark.parametrize(
    ("chunk_name", "sequence_ids"),
    _EPISODE_CHAIN_CHUNKS,
    ids=[chunk_name for chunk_name, _ in _EPISODE_CHAIN_CHUNKS],
)
@pytest.mark.parametrize("run_id", [1, 2, 3])
def test_phase_f_offline_ablation_episode_chain_chunk_produces_interval(
    chunk_name: str,
    sequence_ids: tuple[str, ...],
    run_id: int,
) -> None:
    assert chunk_name
    interval = evaluate_offline_maintenance_ablation_run(
        run_id=run_id,
        families=("episode_chain",),
        sequence_ids=sequence_ids,
    )

    assert interval.sample_count == 1
    assert len(interval.raw_diffs) == interval.sample_count
    assert interval.ci_lower <= interval.mean_diff <= interval.ci_upper
