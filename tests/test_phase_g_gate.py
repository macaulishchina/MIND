from __future__ import annotations

from mind.eval import assert_strategy_gate, evaluate_strategy_gate


def test_phase_g_gate_passes_current_thresholds() -> None:
    result = evaluate_strategy_gate(repeat_count=3)

    assert_strategy_gate(result)
    assert result.g1_pass
    assert result.g2_pass
    assert result.g3_pass
    assert result.g4_pass
    assert result.g5_pass
    assert result.strategy_gate_pass
    assert tuple(item.family for item in result.family_improvements) == (
        "cross_episode_pair",
        "episode_chain",
    )
