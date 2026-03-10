"""Phase F benchmark comparison helpers."""

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
from .baselines import (
    FixedSummaryMemoryBaselineSystem,
    NoMemoryBaselineSystem,
    PlainRagBaselineSystem,
)
from .mind_system import MindLongHorizonSystem
from .reporting import BenchmarkSuiteReport, build_benchmark_suite_report
from .runner import LongHorizonBenchmarkRunner

_COMPARISON_SCHEMA_VERSION = "phase_f_comparison_report_v1"


@dataclass(frozen=True)
class ComparisonInterval:
    mean_diff: float
    ci_lower: float
    ci_upper: float
    sample_count: int
    raw_diffs: tuple[float, ...]


@dataclass(frozen=True)
class PhaseFComparisonResult:
    suite_report: BenchmarkSuiteReport
    versus_no_memory: ComparisonInterval
    versus_fixed_summary_memory: ComparisonInterval
    versus_plain_rag: ComparisonInterval

    @property
    def f2_pass(self) -> bool:
        system_ids = {report.system_id for report in self.suite_report.system_reports}
        return {
            "mind",
            "no_memory",
            "fixed_summary_memory",
            "plain_rag",
        } <= system_ids

    @property
    def f3_pass(self) -> bool:
        return self.suite_report.repeat_count >= 3

    @property
    def f4_pass(self) -> bool:
        return self.versus_no_memory.mean_diff >= 0.10 and self.versus_no_memory.ci_lower > 0.0

    @property
    def f5_pass(self) -> bool:
        return (
            self.versus_fixed_summary_memory.mean_diff >= 0.05
            and self.versus_fixed_summary_memory.ci_lower > 0.0
        )

    @property
    def f6_pass(self) -> bool:
        return self.versus_plain_rag.mean_diff >= -0.02

    @property
    def phase_f_comparison_pass(self) -> bool:
        return self.f2_pass and self.f3_pass and self.f4_pass and self.f5_pass and self.f6_pass


@dataclass(frozen=True)
class PhaseFGateResult:
    manifest_hash: str
    manifest_sequence_count: int
    manifest_min_step_count: int
    manifest_max_step_count: int
    comparison_result: PhaseFComparisonResult
    workspace_ablation: ComparisonInterval
    offline_maintenance_ablation: ComparisonInterval

    @property
    def f1_pass(self) -> bool:
        return (
            self.manifest_sequence_count >= 50
            and 5 <= self.manifest_min_step_count <= self.manifest_max_step_count <= 10
            and len(self.manifest_hash) == 64
        )

    @property
    def f2_pass(self) -> bool:
        return self.comparison_result.f2_pass

    @property
    def f3_pass(self) -> bool:
        return self.comparison_result.f3_pass

    @property
    def f4_pass(self) -> bool:
        return self.comparison_result.f4_pass

    @property
    def f5_pass(self) -> bool:
        return self.comparison_result.f5_pass

    @property
    def f6_pass(self) -> bool:
        return self.comparison_result.f6_pass

    @property
    def f7_pass(self) -> bool:
        return (
            self.workspace_ablation.mean_diff >= 0.03
            and self.workspace_ablation.ci_lower >= 0.03
            and self.offline_maintenance_ablation.mean_diff >= 0.03
            and self.offline_maintenance_ablation.ci_lower >= 0.03
        )

    @property
    def phase_f_pass(self) -> bool:
        return (
            self.f1_pass
            and self.f2_pass
            and self.f3_pass
            and self.f4_pass
            and self.f5_pass
            and self.f6_pass
            and self.f7_pass
        )


def evaluate_phase_f_comparison(*, repeat_count: int = 3) -> PhaseFComparisonResult:
    """Run the current MIND system against the three Phase F baselines."""

    sequences = build_long_horizon_eval_v1()
    manifest = build_long_horizon_eval_manifest_v1()
    runner = LongHorizonBenchmarkRunner(sequences=sequences, manifest=manifest)
    mind_system = MindLongHorizonSystem()
    try:
        suite_report = build_benchmark_suite_report(
            runs_by_system={
                "mind": runner.run_many(
                    system_id="mind",
                    system=mind_system,
                    repeat_count=repeat_count,
                ),
                "no_memory": runner.run_many(
                    system_id="no_memory",
                    system=NoMemoryBaselineSystem(),
                    repeat_count=repeat_count,
                ),
                "fixed_summary_memory": runner.run_many(
                    system_id="fixed_summary_memory",
                    system=FixedSummaryMemoryBaselineSystem(),
                    repeat_count=repeat_count,
                ),
                "plain_rag": runner.run_many(
                    system_id="plain_rag",
                    system=PlainRagBaselineSystem(),
                    repeat_count=repeat_count,
                ),
            }
        )
    finally:
        mind_system.close()

    report_by_system = {report.system_id: report for report in suite_report.system_reports}
    return PhaseFComparisonResult(
        suite_report=suite_report,
        versus_no_memory=_comparison_interval(
            report_by_system["mind"].pus.raw_values,
            report_by_system["no_memory"].pus.raw_values,
        ),
        versus_fixed_summary_memory=_comparison_interval(
            report_by_system["mind"].pus.raw_values,
            report_by_system["fixed_summary_memory"].pus.raw_values,
        ),
        versus_plain_rag=_comparison_interval(
            report_by_system["mind"].pus.raw_values,
            report_by_system["plain_rag"].pus.raw_values,
        ),
    )


def assert_phase_f_comparison(result: PhaseFComparisonResult) -> None:
    if not result.f2_pass:
        raise RuntimeError("F-2 failed: not all required systems are present")
    if not result.f3_pass:
        raise RuntimeError("F-3 failed: repeat_count must be >= 3")
    if not result.f4_pass:
        raise RuntimeError(
            "F-4 failed: MIND vs no-memory "
            f"(mean_diff={result.versus_no_memory.mean_diff:.4f}, "
            f"ci_lower={result.versus_no_memory.ci_lower:.4f})"
        )
    if not result.f5_pass:
        raise RuntimeError(
            "F-5 failed: MIND vs fixed summary memory "
            f"(mean_diff={result.versus_fixed_summary_memory.mean_diff:.4f}, "
            f"ci_lower={result.versus_fixed_summary_memory.ci_lower:.4f})"
        )
    if not result.f6_pass:
        raise RuntimeError(
            "F-6 failed: MIND vs plain RAG "
            f"(mean_diff={result.versus_plain_rag.mean_diff:.4f})"
        )


def evaluate_phase_f_gate(*, repeat_count: int = 3) -> PhaseFGateResult:
    """Run the full local Phase F gate, including F-7 ablations."""

    manifest = build_long_horizon_eval_manifest_v1()
    comparison_result = evaluate_phase_f_comparison(repeat_count=repeat_count)
    sequences = build_long_horizon_eval_v1()
    runner = LongHorizonBenchmarkRunner(sequences=sequences, manifest=manifest)

    full_mind = next(
        system_report
        for system_report in comparison_result.suite_report.system_reports
        if system_report.system_id == "mind"
    )

    workspace_ablation_system = MindLongHorizonSystem(use_workspace=False)
    offline_ablation_system = MindLongHorizonSystem(use_offline_maintenance=False)
    try:
        workspace_ablation_runs = runner.run_many(
            system_id="mind_without_workspace",
            system=workspace_ablation_system,
            repeat_count=repeat_count,
        )
        offline_ablation_runs = runner.run_many(
            system_id="mind_without_offline_maintenance",
            system=offline_ablation_system,
            repeat_count=repeat_count,
        )
    finally:
        workspace_ablation_system.close()
        offline_ablation_system.close()

    workspace_ablation = _comparison_interval(
        full_mind.pus.raw_values,
        tuple(run.average_pus for run in workspace_ablation_runs),
    )
    offline_maintenance_ablation = _comparison_interval(
        full_mind.pus.raw_values,
        tuple(run.average_pus for run in offline_ablation_runs),
    )
    return PhaseFGateResult(
        manifest_hash=manifest.fixture_hash,
        manifest_sequence_count=manifest.sequence_count,
        manifest_min_step_count=manifest.min_step_count,
        manifest_max_step_count=manifest.max_step_count,
        comparison_result=comparison_result,
        workspace_ablation=workspace_ablation,
        offline_maintenance_ablation=offline_maintenance_ablation,
    )


def assert_phase_f_gate(result: PhaseFGateResult) -> None:
    if not result.f1_pass:
        raise RuntimeError(
            "F-1 failed: LongHorizonEval manifest invalid "
            f"(sequence_count={result.manifest_sequence_count}, "
            f"step_range={result.manifest_min_step_count}..{result.manifest_max_step_count})"
        )
    assert_phase_f_comparison(result.comparison_result)
    if not result.f7_pass:
        raise RuntimeError(
            "F-7 failed: component ablation did not drop enough PUS "
            f"(workspace_drop={result.workspace_ablation.mean_diff:.4f}, "
            f"offline_drop={result.offline_maintenance_ablation.mean_diff:.4f})"
        )


def write_phase_f_comparison_report_json(
    path: str | Path,
    result: PhaseFComparisonResult,
) -> Path:
    """Persist the Phase F comparison result as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": _COMPARISON_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "suite_report": _suite_report_to_dict(result.suite_report),
        "versus_no_memory": _comparison_interval_to_dict(result.versus_no_memory),
        "versus_fixed_summary_memory": _comparison_interval_to_dict(
            result.versus_fixed_summary_memory
        ),
        "versus_plain_rag": _comparison_interval_to_dict(result.versus_plain_rag),
        "f2_pass": result.f2_pass,
        "f3_pass": result.f3_pass,
        "f4_pass": result.f4_pass,
        "f5_pass": result.f5_pass,
        "f6_pass": result.f6_pass,
        "phase_f_comparison_pass": result.phase_f_comparison_pass,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def write_phase_f_gate_report_json(
    path: str | Path,
    result: PhaseFGateResult,
) -> Path:
    """Persist the full Phase F gate result as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "phase_f_gate_report_v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "manifest_hash": result.manifest_hash,
        "manifest_sequence_count": result.manifest_sequence_count,
        "manifest_step_range": [
            result.manifest_min_step_count,
            result.manifest_max_step_count,
        ],
        "comparison_report": {
            "versus_no_memory": _comparison_interval_to_dict(
                result.comparison_result.versus_no_memory
            ),
            "versus_fixed_summary_memory": _comparison_interval_to_dict(
                result.comparison_result.versus_fixed_summary_memory
            ),
            "versus_plain_rag": _comparison_interval_to_dict(
                result.comparison_result.versus_plain_rag
            ),
        },
        "workspace_ablation": _comparison_interval_to_dict(result.workspace_ablation),
        "offline_maintenance_ablation": _comparison_interval_to_dict(
            result.offline_maintenance_ablation
        ),
        "f1_pass": result.f1_pass,
        "f2_pass": result.f2_pass,
        "f3_pass": result.f3_pass,
        "f4_pass": result.f4_pass,
        "f5_pass": result.f5_pass,
        "f6_pass": result.f6_pass,
        "f7_pass": result.f7_pass,
        "phase_f_pass": result.phase_f_pass,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def comparison_interval(
    left: tuple[float, ...],
    right: tuple[float, ...],
) -> ComparisonInterval:
    """Compute a paired diff interval from matched sample vectors."""
    if len(left) != len(right):
        raise ValueError("comparison intervals require matched sample counts")
    raw_diffs = tuple(round(a - b, 4) for a, b in zip(left, right, strict=True))
    center = round(mean(raw_diffs), 4)
    ci_lower = min(raw_diffs)
    ci_upper = max(raw_diffs)
    return ComparisonInterval(
        mean_diff=center,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        sample_count=len(raw_diffs),
        raw_diffs=raw_diffs,
    )


# Keep the private alias for internal backward compatibility.
_comparison_interval = comparison_interval


def comparison_interval_to_dict(interval: ComparisonInterval) -> dict[str, object]:
    """Serialize a ``ComparisonInterval`` to a JSON-friendly dict."""
    return {
        "mean_diff": interval.mean_diff,
        "ci_lower": interval.ci_lower,
        "ci_upper": interval.ci_upper,
        "sample_count": interval.sample_count,
        "raw_diffs": list(interval.raw_diffs),
    }


# Keep the private alias for internal backward compatibility.
_comparison_interval_to_dict = comparison_interval_to_dict


def _suite_report_to_dict(report: BenchmarkSuiteReport) -> dict[str, Any]:
    return {
        "schema_version": report.schema_version,
        "generated_at": report.generated_at,
        "fixture_name": report.fixture_name,
        "fixture_hash": report.fixture_hash,
        "repeat_count": report.repeat_count,
        "system_reports": [
            {
                "system_id": system_report.system_id,
                "repeat_count": system_report.repeat_count,
                "task_success_rate": {
                    "mean": system_report.task_success_rate.mean,
                    "ci_lower": system_report.task_success_rate.ci_lower,
                    "ci_upper": system_report.task_success_rate.ci_upper,
                    "raw_values": list(system_report.task_success_rate.raw_values),
                },
                "gold_fact_coverage": {
                    "mean": system_report.gold_fact_coverage.mean,
                    "ci_lower": system_report.gold_fact_coverage.ci_lower,
                    "ci_upper": system_report.gold_fact_coverage.ci_upper,
                    "raw_values": list(system_report.gold_fact_coverage.raw_values),
                },
                "reuse_rate": {
                    "mean": system_report.reuse_rate.mean,
                    "ci_lower": system_report.reuse_rate.ci_lower,
                    "ci_upper": system_report.reuse_rate.ci_upper,
                    "raw_values": list(system_report.reuse_rate.raw_values),
                },
                "context_cost_ratio": {
                    "mean": system_report.context_cost_ratio.mean,
                    "ci_lower": system_report.context_cost_ratio.ci_lower,
                    "ci_upper": system_report.context_cost_ratio.ci_upper,
                    "raw_values": list(system_report.context_cost_ratio.raw_values),
                },
                "maintenance_cost_ratio": {
                    "mean": system_report.maintenance_cost_ratio.mean,
                    "ci_lower": system_report.maintenance_cost_ratio.ci_lower,
                    "ci_upper": system_report.maintenance_cost_ratio.ci_upper,
                    "raw_values": list(system_report.maintenance_cost_ratio.raw_values),
                },
                "pollution_rate": {
                    "mean": system_report.pollution_rate.mean,
                    "ci_lower": system_report.pollution_rate.ci_lower,
                    "ci_upper": system_report.pollution_rate.ci_upper,
                    "raw_values": list(system_report.pollution_rate.raw_values),
                },
                "pus": {
                    "mean": system_report.pus.mean,
                    "ci_lower": system_report.pus.ci_lower,
                    "ci_upper": system_report.pus.ci_upper,
                    "raw_values": list(system_report.pus.raw_values),
                },
            }
            for system_report in report.system_reports
        ],
    }
