from __future__ import annotations

from pathlib import Path

from mind.eval import (
    evaluate_fixed_rule_cost_report,
    read_strategy_cost_report_json,
    write_strategy_cost_report_json,
)


def test_phase_g_cost_report_round_trips(tmp_path: Path) -> None:
    report = evaluate_fixed_rule_cost_report(repeat_count=3)

    output_path = write_strategy_cost_report_json(tmp_path / "phase_g_cost_report.json", report)
    reloaded = read_strategy_cost_report_json(output_path)

    assert reloaded == report


def test_phase_g_cost_report_freezes_fixed_rule_budget_profile() -> None:
    report = evaluate_fixed_rule_cost_report(repeat_count=3)

    assert report.schema_version == "strategy_cost_report_v1"
    assert report.strategy_id == "fixed_rule_v1"
    assert report.budget_profile.profile_id == "strategy_fixed_rule_budget_v1"
    assert report.budget_profile.fixture_hash == report.fixture_hash
    assert report.token_budget_bias.mean == 0.0
    assert report.storage_budget_bias.mean == 0.0
    assert report.maintenance_budget_bias.mean == 0.0
    assert report.total_budget_bias.mean == 0.0
    assert all(snapshot.strategy_id == "fixed_rule_v1" for snapshot in report.snapshots)
    assert all(snapshot.storage_cost_ratio >= 1.0 for snapshot in report.snapshots)
