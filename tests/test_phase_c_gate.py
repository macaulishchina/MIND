from __future__ import annotations

from mind.fixtures.primitive_golden_calls import build_primitive_golden_calls_v1
from mind.primitives.gate import assert_primitive_gate, evaluate_primitive_gate


def test_primitive_golden_calls_v1_has_required_coverage() -> None:
    calls = build_primitive_golden_calls_v1()

    assert len(calls) == 200
    assert sum("smoke" in call.expectation.tags for call in calls) == 7
    assert sum("budget" in call.expectation.tags for call in calls) == 50
    assert sum("rollback" in call.expectation.tags for call in calls) == 50


def test_phase_c_gate_metrics() -> None:
    result = evaluate_primitive_gate()

    assert result.total_calls == 200
    assert result.expectation_match_count == result.total_calls
    assert result.schema_valid_calls == result.total_calls
    assert result.structured_log_calls == result.total_calls
    assert result.smoke_success_count == 7
    assert result.budget_rejection_match_count == 50
    assert result.budget_total == 50
    assert result.rollback_atomic_count == 50
    assert result.rollback_total == 50
    assert result.c1_pass
    assert result.c2_pass
    assert result.c3_pass
    assert result.c4_pass
    assert result.c5_pass
    assert result.primitive_gate_pass
    assert_primitive_gate(result)
