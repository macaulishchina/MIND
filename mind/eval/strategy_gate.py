"""Strategy optimization evaluation and gate helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from ..fixtures.long_horizon_eval import (
    build_long_horizon_eval_manifest_v1,
    build_long_horizon_eval_v1,
)
from .benchmark_gate import ComparisonInterval, comparison_interval, comparison_interval_to_dict
from .costing import (
    StrategyCostReport,
    build_cost_budget_profile,
    build_strategy_cost_report,
)
from .mind_system import MindLongHorizonSystem
from .reporting import BenchmarkSuiteReport, BenchmarkSystemReport, build_benchmark_suite_report
from .runner import LongHorizonBenchmarkRun, LongHorizonBenchmarkRunner
from .strategy import FixedRuleMindStrategy, OptimizedMindStrategy

_SCHEMA_VERSION = "strategy_gate_report_v1"


@dataclass(frozen=True)
class StrategyFamilyImprovement:
    family: str
    fixed_rule_pus: float
    optimized_pus: float
    pus_delta: ComparisonInterval


@dataclass(frozen=True)
class StrategyGateResult:
    manifest_hash: str
    repeat_count: int
    suite_report: BenchmarkSuiteReport
    fixed_rule_cost_report: StrategyCostReport
    optimized_cost_report: StrategyCostReport
    pus_improvement: ComparisonInterval
    family_improvements: tuple[StrategyFamilyImprovement, ...]
    pollution_rate_delta: ComparisonInterval

    @property
    def g1_pass(self) -> bool:
        return self.pus_improvement.mean_diff >= 0.05

    @property
    def g2_pass(self) -> bool:
        return all(
            _budget_bias_within_limit(interval)
            for interval in (
                self.optimized_cost_report.token_budget_bias,
                self.optimized_cost_report.storage_budget_bias,
                self.optimized_cost_report.maintenance_budget_bias,
                self.optimized_cost_report.total_budget_bias,
            )
        )

    @property
    def g3_pass(self) -> bool:
        return sum(result.pus_delta.mean_diff > 0.0 for result in self.family_improvements) >= 2

    @property
    def g4_pass(self) -> bool:
        return self.pollution_rate_delta.ci_upper <= 0.02

    @property
    def g5_pass(self) -> bool:
        return self.repeat_count >= 3 and self.pus_improvement.ci_lower > 0.0

    @property
    def strategy_gate_pass(self) -> bool:
        return self.g1_pass and self.g2_pass and self.g3_pass and self.g4_pass and self.g5_pass


def evaluate_strategy_gate(*, repeat_count: int = 3) -> StrategyGateResult:
    """Run the formal strategy optimization gate on LongHorizonEval v1."""

    manifest = build_long_horizon_eval_manifest_v1()
    sequences = build_long_horizon_eval_v1()
    runner = LongHorizonBenchmarkRunner(sequences=sequences, manifest=manifest)
    fixed_system = MindLongHorizonSystem(strategy=FixedRuleMindStrategy())
    optimized_system = MindLongHorizonSystem(strategy=OptimizedMindStrategy())
    try:
        fixed_runs = runner.run_many(
            system_id="mind_fixed_rule",
            system=fixed_system,
            repeat_count=repeat_count,
        )
        optimized_runs = runner.run_many(
            system_id="mind_optimized_v1",
            system=optimized_system,
            repeat_count=repeat_count,
        )
        fixed_snapshots = tuple(fixed_system.cost_snapshot(run.run_id) for run in fixed_runs)
        optimized_snapshots = tuple(
            optimized_system.cost_snapshot(run.run_id) for run in optimized_runs
        )
    finally:
        fixed_system.close()
        optimized_system.close()

    suite_report = build_benchmark_suite_report(
        runs_by_system={
            "mind_fixed_rule": fixed_runs,
            "mind_optimized_v1": optimized_runs,
        }
    )
    budget_profile = build_cost_budget_profile(
        profile_id="strategy_fixed_rule_budget_v1",
        fixture_name=manifest.fixture_name,
        fixture_hash=manifest.fixture_hash,
        runs=fixed_runs,
        snapshots=fixed_snapshots,
    )
    fixed_rule_cost_report = build_strategy_cost_report(
        system_id="mind_fixed_rule",
        strategy_id="fixed_rule_v1",
        runs=fixed_runs,
        snapshots=fixed_snapshots,
        budget_profile=budget_profile,
    )
    optimized_cost_report = build_strategy_cost_report(
        system_id="mind_optimized_v1",
        strategy_id="optimized_v1",
        runs=optimized_runs,
        snapshots=optimized_snapshots,
        budget_profile=budget_profile,
    )

    fixed_report = _system_report(suite_report, "mind_fixed_rule")
    optimized_report = _system_report(suite_report, "mind_optimized_v1")
    family_improvements = tuple(
        _family_improvement(family, fixed_runs, optimized_runs)
        for family in sorted({sequence.family for sequence in sequences})
    )
    return StrategyGateResult(
        manifest_hash=manifest.fixture_hash,
        repeat_count=repeat_count,
        suite_report=suite_report,
        fixed_rule_cost_report=fixed_rule_cost_report,
        optimized_cost_report=optimized_cost_report,
        pus_improvement=_comparison_interval(
            optimized_report.pus.raw_values,
            fixed_report.pus.raw_values,
        ),
        family_improvements=family_improvements,
        pollution_rate_delta=_comparison_interval(
            optimized_report.pollution_rate.raw_values,
            fixed_report.pollution_rate.raw_values,
        ),
    )


def assert_strategy_gate(result: StrategyGateResult) -> None:
    if not result.g1_pass:
        raise RuntimeError(
            "G-1 failed: optimized strategy did not improve enough PUS "
            f"(mean_diff={result.pus_improvement.mean_diff:.4f})"
        )
    if not result.g2_pass:
        raise RuntimeError(
            "G-2 failed: optimized strategy drifted outside the 5% budget envelope "
            f"(token_bias={result.optimized_cost_report.token_budget_bias.mean:.4f}, "
            f"storage_bias={result.optimized_cost_report.storage_budget_bias.mean:.4f}, "
            "maintenance_bias="
            f"{result.optimized_cost_report.maintenance_budget_bias.mean:.4f}, "
            f"total_bias={result.optimized_cost_report.total_budget_bias.mean:.4f})"
        )
    if not result.g3_pass:
        families = ", ".join(
            f"{item.family}={item.pus_delta.mean_diff:.4f}" for item in result.family_improvements
        )
        raise RuntimeError(
            "G-3 failed: optimized strategy did not generalize across >= 2 families "
            f"({families})"
        )
    if not result.g4_pass:
        raise RuntimeError(
            "G-4 failed: optimized strategy increased pollution too much "
            f"(ci_upper={result.pollution_rate_delta.ci_upper:.4f})"
        )
    if not result.g5_pass:
        raise RuntimeError(
            "G-5 failed: repeated runs are not stably better than fixed-rule "
            f"(repeat_count={result.repeat_count}, "
            f"ci_lower={result.pus_improvement.ci_lower:.4f})"
        )


def write_strategy_gate_report_json(
    path: str | Path,
    result: StrategyGateResult,
) -> Path:
    """Persist the full strategy gate result as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "manifest_hash": result.manifest_hash,
        "repeat_count": result.repeat_count,
        "pus_improvement": _comparison_interval_to_dict(result.pus_improvement),
        "family_improvements": [
            {
                "family": item.family,
                "fixed_rule_pus": item.fixed_rule_pus,
                "optimized_pus": item.optimized_pus,
                "pus_delta": _comparison_interval_to_dict(item.pus_delta),
            }
            for item in result.family_improvements
        ],
        "pollution_rate_delta": _comparison_interval_to_dict(result.pollution_rate_delta),
        "fixed_rule_cost_report": _cost_report_summary(result.fixed_rule_cost_report),
        "optimized_cost_report": _cost_report_summary(result.optimized_cost_report),
        "suite_report": {
            "fixture_name": result.suite_report.fixture_name,
            "fixture_hash": result.suite_report.fixture_hash,
            "repeat_count": result.suite_report.repeat_count,
            "system_reports": [
                _system_report_summary(system_report)
                for system_report in result.suite_report.system_reports
            ],
        },
        "g1_pass": result.g1_pass,
        "g2_pass": result.g2_pass,
        "g3_pass": result.g3_pass,
        "g4_pass": result.g4_pass,
        "g5_pass": result.g5_pass,
        "strategy_gate_pass": result.strategy_gate_pass,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def _family_improvement(
    family: str,
    fixed_runs: tuple[LongHorizonBenchmarkRun, ...],
    optimized_runs: tuple[LongHorizonBenchmarkRun, ...],
) -> StrategyFamilyImprovement:
    fixed_pus = _family_pus_values(fixed_runs, family)
    optimized_pus = _family_pus_values(optimized_runs, family)
    return StrategyFamilyImprovement(
        family=family,
        fixed_rule_pus=round(mean(fixed_pus), 4),
        optimized_pus=round(mean(optimized_pus), 4),
        pus_delta=_comparison_interval(optimized_pus, fixed_pus),
    )


def _family_pus_values(
    runs: tuple[LongHorizonBenchmarkRun, ...],
    family: str,
) -> tuple[float, ...]:
    values: list[float] = []
    for run in runs:
        family_results = [
            result.score_card.pus for result in run.sequence_results if result.family == family
        ]
        if not family_results:
            raise ValueError(f"family {family!r} missing from run {run.run_id}")
        values.append(round(mean(family_results), 4))
    return tuple(values)


def _system_report(
    suite_report: BenchmarkSuiteReport,
    system_id: str,
) -> BenchmarkSystemReport:
    return next(
        report for report in suite_report.system_reports if report.system_id == system_id
    )


def _budget_bias_within_limit(interval: Any) -> bool:
    return max(abs(interval.ci_lower), abs(interval.ci_upper)) <= 0.05


# Use the shared benchmark comparison helpers to avoid duplication.
_comparison_interval = comparison_interval
_comparison_interval_to_dict = comparison_interval_to_dict


def _cost_report_summary(report: StrategyCostReport) -> dict[str, object]:
    return {
        "system_id": report.system_id,
        "strategy_id": report.strategy_id,
        "repeat_count": report.repeat_count,
        "budget_profile": {
            "profile_id": report.budget_profile.profile_id,
            "token_budget_ratio": report.budget_profile.token_budget_ratio,
            "storage_budget_ratio": report.budget_profile.storage_budget_ratio,
            "maintenance_budget_ratio": report.budget_profile.maintenance_budget_ratio,
            "total_budget_ratio": report.budget_profile.total_budget_ratio,
        },
        "token_budget_bias": _metric_summary(report.token_budget_bias),
        "storage_budget_bias": _metric_summary(report.storage_budget_bias),
        "maintenance_budget_bias": _metric_summary(report.maintenance_budget_bias),
        "total_budget_bias": _metric_summary(report.total_budget_bias),
    }


def _system_report_summary(system_report: BenchmarkSystemReport) -> dict[str, object]:
    return {
        "system_id": system_report.system_id,
        "pus": _metric_summary(system_report.pus),
        "task_success_rate": _metric_summary(system_report.task_success_rate),
        "gold_fact_coverage": _metric_summary(system_report.gold_fact_coverage),
        "reuse_rate": _metric_summary(system_report.reuse_rate),
        "context_cost_ratio": _metric_summary(system_report.context_cost_ratio),
        "maintenance_cost_ratio": _metric_summary(system_report.maintenance_cost_ratio),
        "pollution_rate": _metric_summary(system_report.pollution_rate),
    }


def _metric_summary(interval: Any) -> dict[str, object]:
    return {
        "mean": interval.mean,
        "ci_lower": interval.ci_lower,
        "ci_upper": interval.ci_upper,
        "raw_values": list(interval.raw_values),
    }
