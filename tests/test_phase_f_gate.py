from __future__ import annotations

from mind.eval import assert_phase_f_gate, evaluate_phase_f_gate


def test_phase_f_gate_passes_current_thresholds() -> None:
    result = evaluate_phase_f_gate(repeat_count=3)

    assert_phase_f_gate(result)
    assert result.f1_pass
    assert result.f2_pass
    assert result.f3_pass
    assert result.f4_pass
    assert result.f5_pass
    assert result.f6_pass
    assert result.f7_pass
    assert result.phase_f_pass
