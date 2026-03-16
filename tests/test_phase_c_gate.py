from __future__ import annotations

from mind.fixtures.primitive_golden_calls import build_primitive_golden_calls_v1
from mind.primitives.gate import evaluate_primitive_gate


def test_primitive_golden_calls_v1_has_required_coverage() -> None:
    calls = build_primitive_golden_calls_v1()

    assert len(calls) == 200
    assert sum("smoke" in call.expectation.tags for call in calls) == 7
    assert sum("budget" in call.expectation.tags for call in calls) == 50
    assert sum("rollback" in call.expectation.tags for call in calls) == 50


def test_phase_c_general_schema_and_logging_metrics() -> None:
    result = evaluate_primitive_gate(exclude_tags=("smoke", "budget", "rollback"))

    assert result.total_calls == 93
    assert result.expectation_match_count == result.total_calls
    assert result.schema_valid_calls == result.total_calls
    assert result.structured_log_calls == result.total_calls


def test_phase_c_smoke_metrics() -> None:
    result = evaluate_primitive_gate(include_tags=("smoke",))

    assert result.total_calls == 7
    assert result.expectation_match_count == result.total_calls
    assert result.schema_valid_calls == result.total_calls
    assert result.structured_log_calls == result.total_calls
    assert result.smoke_success_count == 7
    assert result.c1_pass


def test_phase_c_budget_metrics() -> None:
    result = evaluate_primitive_gate(include_tags=("budget",))

    assert result.total_calls == 50
    assert result.expectation_match_count == result.total_calls
    assert result.schema_valid_calls == result.total_calls
    assert result.structured_log_calls == result.total_calls
    assert result.budget_rejection_match_count == 50
    assert result.budget_total == 50
    assert result.c4_pass


def test_phase_c_rollback_metrics() -> None:
    result = evaluate_primitive_gate(include_tags=("rollback",))

    assert result.total_calls == 50
    assert result.expectation_match_count == result.total_calls
    assert result.schema_valid_calls == result.total_calls
    assert result.structured_log_calls == result.total_calls
    assert result.rollback_atomic_count == 50
    assert result.rollback_total == 50
    assert result.c5_pass
