from __future__ import annotations

import pytest

from mind.eval import evaluate_strategy_family_run


@pytest.mark.parametrize("run_id", [1, 2, 3])
def test_phase_g_episode_chain_run_sustains_strategy_improvement(run_id: int) -> None:
    result = evaluate_strategy_family_run(family="episode_chain", run_id=run_id)

    assert result.g1_pass
    assert result.g2_pass
    assert result.g4_pass
    assert result.repeat_count == 1
    assert tuple(item.family for item in result.family_improvements) == ("episode_chain",)
    assert result.family_improvements[0].pus_delta.mean_diff > 0.0
