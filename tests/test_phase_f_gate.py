from __future__ import annotations

from mind.eval import assert_benchmark_gate, evaluate_benchmark_gate


def test_phase_f_gate_passes_current_thresholds() -> None:
    result = evaluate_benchmark_gate(repeat_count=3)

    assert_benchmark_gate(result)
    assert result.f1_pass
    assert result.f2_pass
    assert result.f3_pass
    assert result.f4_pass
    assert result.f5_pass
    assert result.f6_pass
    assert result.f7_pass
    assert result.benchmark_gate_pass
