"""Tests for Phase α-4: Growth Metrics.

Covers:
- GrowthLiftResult.compute correctness and edge cases
- MemoryEfficiencyResult.compute correctness and zero-object guard
- FeedbackCorrelationResult.compute correctness
- GrowthPhaseAlphaReport.alpha_gate_pass logic
- run_growth_eval script exists
"""

from __future__ import annotations

from pathlib import Path

from mind.eval.growth_metrics import (
    FeedbackCorrelationResult,
    GrowthLiftResult,
    GrowthPhaseAlphaReport,
    MemoryEfficiencyResult,
)
from mind.eval.runner import LongHorizonBenchmarkRun

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bench_run(
    *,
    average_pus: float = 0.5,
    average_task_success_rate: float = 0.6,
    sequence_count: int = 10,
) -> LongHorizonBenchmarkRun:
    """Create a minimal LongHorizonBenchmarkRun for metric computation."""
    return LongHorizonBenchmarkRun(
        system_id="test-system",
        run_id=1,
        fixture_name="test-fixture",
        fixture_hash="abc123",
        sequence_count=sequence_count,
        average_task_success_rate=average_task_success_rate,
        average_gold_fact_coverage=0.5,
        average_reuse_rate=0.5,
        average_context_cost_ratio=0.5,
        average_maintenance_cost_ratio=0.1,
        average_pollution_rate=0.0,
        average_pus=average_pus,
        sequence_results=(),
    )


# ---------------------------------------------------------------------------
# GrowthLift
# ---------------------------------------------------------------------------


class TestGrowthLift:
    def test_positive_lift(self) -> None:
        with_maint = _bench_run(average_pus=0.7)
        without_maint = _bench_run(average_pus=0.5)
        result = GrowthLiftResult.compute(with_maint, without_maint)
        assert result.growth_lift > 0
        assert result.growth_lift == round(0.7 - 0.5, 4)

    def test_negative_lift(self) -> None:
        with_maint = _bench_run(average_pus=0.3)
        without_maint = _bench_run(average_pus=0.5)
        result = GrowthLiftResult.compute(with_maint, without_maint)
        assert result.growth_lift < 0

    def test_zero_lift(self) -> None:
        a = _bench_run(average_pus=0.5)
        b = _bench_run(average_pus=0.5)
        result = GrowthLiftResult.compute(a, b)
        assert result.growth_lift == 0.0


# ---------------------------------------------------------------------------
# MemoryEfficiency
# ---------------------------------------------------------------------------


class TestMemoryEfficiency:
    def test_positive_efficiency(self) -> None:
        run = _bench_run(average_task_success_rate=0.8, sequence_count=10)
        result = MemoryEfficiencyResult.compute(run, total_objects=100)
        assert result.memory_efficiency > 0

    def test_zero_objects_returns_zero(self) -> None:
        run = _bench_run()
        result = MemoryEfficiencyResult.compute(run, total_objects=0)
        assert result.memory_efficiency == 0.0

    def test_formula_correctness(self) -> None:
        run = _bench_run(average_task_success_rate=1.0, sequence_count=10)
        result = MemoryEfficiencyResult.compute(run, total_objects=50)
        expected = round((1.0 * 10) / 50.0, 4)
        assert result.memory_efficiency == expected


# ---------------------------------------------------------------------------
# FeedbackCorrelation
# ---------------------------------------------------------------------------


class TestFeedbackCorrelation:
    def test_positive_dominance(self) -> None:
        result = FeedbackCorrelationResult.compute(
            positive_object_ids={"obj-1", "obj-2"},
            negative_object_ids=set(),
            selected_ids_per_step=[["obj-1", "obj-2"], ["obj-1"]],
        )
        assert result.feedback_correlation > 0
        assert result.positive_reuse_rate > 0
        assert result.negative_reuse_rate == 0.0

    def test_negative_dominance(self) -> None:
        result = FeedbackCorrelationResult.compute(
            positive_object_ids=set(),
            negative_object_ids={"obj-1"},
            selected_ids_per_step=[["obj-1"]],
        )
        assert result.feedback_correlation < 0

    def test_empty_steps_returns_zero(self) -> None:
        result = FeedbackCorrelationResult.compute(
            positive_object_ids={"obj-1"},
            negative_object_ids=set(),
            selected_ids_per_step=[],
        )
        assert result.feedback_correlation == 0.0
        assert result.positive_reuse_rate == 0.0


# ---------------------------------------------------------------------------
# GrowthPhaseAlphaReport
# ---------------------------------------------------------------------------


class TestGrowthPhaseAlphaReport:
    def test_alpha_gate_pass_positive(self) -> None:
        report = GrowthPhaseAlphaReport(
            growth_lift=GrowthLiftResult.compute(
                _bench_run(average_pus=0.6),
                _bench_run(average_pus=0.5),
            ),
            memory_efficiency=MemoryEfficiencyResult.compute(
                _bench_run(average_task_success_rate=0.8, sequence_count=10),
                total_objects=50,
            ),
            feedback_correlation=FeedbackCorrelationResult.compute(
                positive_object_ids={"a"},
                negative_object_ids=set(),
                selected_ids_per_step=[["a"]],
            ),
        )
        assert report.alpha_gate_pass is True

    def test_alpha_gate_fails_on_negative_lift(self) -> None:
        report = GrowthPhaseAlphaReport(
            growth_lift=GrowthLiftResult.compute(
                _bench_run(average_pus=0.3),
                _bench_run(average_pus=0.5),
            ),
            memory_efficiency=MemoryEfficiencyResult.compute(
                _bench_run(), total_objects=50,
            ),
            feedback_correlation=FeedbackCorrelationResult.compute(
                positive_object_ids=set(),
                negative_object_ids=set(),
                selected_ids_per_step=[],
            ),
        )
        assert report.alpha_gate_pass is False


# ---------------------------------------------------------------------------
# Script exists
# ---------------------------------------------------------------------------


class TestGrowthEvalScript:
    def test_script_file_exists(self) -> None:
        script = Path("scripts/run_growth_eval.py")
        assert script.exists(), f"Missing expected script: {script}"
