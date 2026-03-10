from __future__ import annotations

from pathlib import Path

from mind.eval.phase_f import assert_phase_f_comparison, evaluate_phase_f_comparison


def test_phase_f_comparison_passes_current_thresholds(tmp_path: Path) -> None:
    del tmp_path
    result = evaluate_phase_f_comparison(repeat_count=3)

    assert_phase_f_comparison(result)
    assert result.f2_pass
    assert result.f3_pass
    assert result.f4_pass
    assert result.f5_pass
    assert result.f6_pass
    assert result.phase_f_comparison_pass
