from __future__ import annotations

from pathlib import Path

from mind.eval.benchmark_gate import assert_benchmark_comparison, evaluate_benchmark_comparison


def test_benchmark_comparison_passes_current_thresholds(tmp_path: Path) -> None:
    del tmp_path
    result = evaluate_benchmark_comparison(repeat_count=3)

    assert_benchmark_comparison(result)
    assert result.f2_pass
    assert result.f3_pass
    assert result.f4_pass
    assert result.f5_pass
    assert result.f6_pass
    assert result.benchmark_comparison_pass
