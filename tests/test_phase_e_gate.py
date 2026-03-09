from __future__ import annotations

from pathlib import Path

from mind.offline import assert_phase_e_gate, evaluate_phase_e_gate


def test_phase_e_gate_passes(tmp_path: Path) -> None:
    result = evaluate_phase_e_gate(tmp_path / "phase_e_gate.sqlite3")

    assert_phase_e_gate(result)
    assert result.e1_pass
    assert result.e2_pass
    assert result.e3_pass
    assert result.e4_pass
    assert result.e5_pass
    assert result.integrity_report.source_trace_coverage == 1.0
    assert result.startup_result.replay_lift >= 1.5
    assert result.startup_result.schema_validation_precision >= 0.85
    assert result.startup_result.promotion_precision_at_10 >= 0.80
    assert result.dev_eval.pus_improvement >= 0.05
    assert result.dev_eval.pollution_rate_delta <= 0.02
