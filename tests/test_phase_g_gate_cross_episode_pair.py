from __future__ import annotations

import pytest

from mind.eval import evaluate_strategy_family_run
from tests._long_horizon_eval_support import family_sequence_chunks

_CROSS_EPISODE_PAIR_CHUNKS = family_sequence_chunks("cross_episode_pair", chunk_size=5)


@pytest.mark.parametrize(
    ("chunk_name", "sequence_ids"),
    _CROSS_EPISODE_PAIR_CHUNKS,
    ids=[chunk_name for chunk_name, _ in _CROSS_EPISODE_PAIR_CHUNKS],
)
@pytest.mark.parametrize("run_id", [1, 2, 3])
def test_phase_g_cross_episode_pair_chunk_sustains_strategy_improvement(
    chunk_name: str,
    sequence_ids: tuple[str, ...],
    run_id: int,
) -> None:
    assert chunk_name
    result = evaluate_strategy_family_run(
        family="cross_episode_pair",
        run_id=run_id,
        sequence_ids=sequence_ids,
    )

    assert result.g1_pass
    assert result.g2_pass
    assert result.g4_pass
    assert result.repeat_count == 1
    assert tuple(item.family for item in result.family_improvements) == ("cross_episode_pair",)
    assert result.family_improvements[0].pus_delta.mean_diff > 0.0
