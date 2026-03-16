from __future__ import annotations

import pytest

from mind.eval import (
    BenchmarkComparisonResult,
    ComparisonInterval,
    assert_benchmark_gate,
    evaluate_benchmark_gate,
)
from mind.eval.reporting import (
    BenchmarkSuiteReport,
    BenchmarkSystemReport,
    MetricConfidenceInterval,
)
from mind.fixtures.long_horizon_eval import build_long_horizon_eval_manifest_v1


def test_phase_f_manifest_matches_current_thresholds() -> None:
    manifest = build_long_horizon_eval_manifest_v1()

    assert manifest.sequence_count >= 50
    assert 5 <= manifest.min_step_count <= manifest.max_step_count <= 10
    assert len(manifest.fixture_hash) == 64


def test_phase_f_gate_builds_full_result_from_component_evaluations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    comparison_result = _passing_comparison_result()
    workspace_ablation = _interval(0.05, 0.04, 0.06)
    offline_ablation = _interval(0.05, 0.04, 0.06)

    monkeypatch.setattr(
        "mind.eval.benchmark_gate.evaluate_benchmark_comparison",
        lambda repeat_count=3: comparison_result,
    )
    monkeypatch.setattr(
        "mind.eval.benchmark_gate.evaluate_workspace_ablation",
        lambda repeat_count=3, families=None: workspace_ablation,
    )
    monkeypatch.setattr(
        "mind.eval.benchmark_gate.evaluate_offline_maintenance_ablation",
        lambda repeat_count=3, families=None: offline_ablation,
    )

    result = evaluate_benchmark_gate(repeat_count=3)

    assert_benchmark_gate(result)
    assert result.benchmark_gate_pass


def _passing_comparison_result() -> BenchmarkComparisonResult:
    return BenchmarkComparisonResult(
        suite_report=BenchmarkSuiteReport(
            schema_version="benchmark_suite_report_v1",
            generated_at="2026-03-16T00:00:00+00:00",
            fixture_name="long_horizon_eval_v1",
            fixture_hash="a" * 64,
            repeat_count=3,
            system_reports=(
                _system_report("mind"),
                _system_report("no_memory"),
                _system_report("fixed_summary_memory"),
                _system_report("plain_rag"),
            ),
        ),
        versus_no_memory=_interval(0.12, 0.10, 0.14),
        versus_fixed_summary_memory=_interval(0.06, 0.05, 0.07),
        versus_plain_rag=_interval(0.00, -0.01, 0.01),
    )


def _system_report(system_id: str) -> BenchmarkSystemReport:
    return BenchmarkSystemReport(
        system_id=system_id,
        fixture_name="long_horizon_eval_v1",
        fixture_hash="a" * 64,
        repeat_count=3,
        task_success_rate=_metric(0.7),
        gold_fact_coverage=_metric(0.7),
        reuse_rate=_metric(0.7),
        context_cost_ratio=_metric(1.0),
        maintenance_cost_ratio=_metric(1.0),
        pollution_rate=_metric(0.0),
        pus=_metric(0.7),
        runs=(),
    )


def _metric(mean: float) -> MetricConfidenceInterval:
    return MetricConfidenceInterval(
        mean=mean,
        ci_lower=mean,
        ci_upper=mean,
        sample_count=3,
        raw_values=(mean, mean, mean),
    )


def _interval(mean_diff: float, ci_lower: float, ci_upper: float) -> ComparisonInterval:
    return ComparisonInterval(
        mean_diff=mean_diff,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        sample_count=3,
        raw_diffs=(mean_diff, mean_diff, mean_diff),
    )
