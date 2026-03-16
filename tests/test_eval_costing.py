from __future__ import annotations

from pathlib import Path

from mind.eval import (
    CostBudgetProfile,
    StrategyCostReport,
    evaluate_fixed_rule_cost_report,
    read_strategy_cost_report_json,
    write_strategy_cost_report_json,
)
from mind.eval._ci import MetricConfidenceInterval


def test_phase_g_cost_report_round_trips(tmp_path: Path) -> None:
    report = _synthetic_cost_report()

    output_path = write_strategy_cost_report_json(tmp_path / "phase_g_cost_report.json", report)
    reloaded = read_strategy_cost_report_json(output_path)

    assert reloaded == report


def test_phase_g_cost_report_freezes_fixed_rule_budget_profile() -> None:
    report = evaluate_fixed_rule_cost_report(repeat_count=1)

    assert report.schema_version == "strategy_cost_report_v1"
    assert report.strategy_id == "fixed_rule_v1"
    assert report.budget_profile.profile_id == "strategy_fixed_rule_budget_v1"
    assert report.budget_profile.fixture_hash == report.fixture_hash
    assert report.token_budget_bias.mean == 0.0
    assert report.storage_budget_bias.mean == 0.0
    assert report.maintenance_budget_bias.mean == 0.0
    assert report.total_budget_bias.mean == 0.0
    assert len(report.snapshots) == 1
    assert all(snapshot.strategy_id == "fixed_rule_v1" for snapshot in report.snapshots)
    assert all(snapshot.storage_cost_ratio >= 1.0 for snapshot in report.snapshots)


def _synthetic_cost_report() -> StrategyCostReport:
    metric = MetricConfidenceInterval(
        mean=1.0,
        ci_lower=1.0,
        ci_upper=1.0,
        sample_count=3,
        raw_values=(1.0, 1.0, 1.0),
    )
    zero_metric = MetricConfidenceInterval(
        mean=0.0,
        ci_lower=0.0,
        ci_upper=0.0,
        sample_count=3,
        raw_values=(0.0, 0.0, 0.0),
    )
    return StrategyCostReport(
        schema_version="strategy_cost_report_v1",
        generated_at="2026-03-16T00:00:00+00:00",
        fixture_name="LongHorizonEval v1",
        fixture_hash="a" * 64,
        system_id="mind_fixed_rule",
        strategy_id="fixed_rule_v1",
        repeat_count=3,
        budget_profile=CostBudgetProfile(
            profile_id="strategy_fixed_rule_budget_v1",
            fixture_name="LongHorizonEval v1",
            fixture_hash="a" * 64,
            repeat_count=3,
            token_budget_ratio=1.0,
            storage_budget_ratio=1.0,
            maintenance_budget_ratio=1.0,
            total_budget_ratio=1.0,
        ),
        token_cost_ratio=metric,
        storage_cost_ratio=metric,
        maintenance_cost_ratio=metric,
        total_cost_ratio=metric,
        token_budget_bias=zero_metric,
        storage_budget_bias=zero_metric,
        maintenance_budget_bias=zero_metric,
        total_budget_bias=zero_metric,
        snapshots=(),
    )
