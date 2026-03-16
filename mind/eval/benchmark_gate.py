"""Benchmark comparison helpers."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from ..fixtures.long_horizon_eval import (
    LongHorizonEvalManifest,
    LongHorizonEvalSequence,
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

_COMPARISON_SCHEMA_VERSION = "benchmark_comparison_report_v1"


@dataclass(frozen=True)
class ComparisonInterval:
    mean_diff: float
    ci_lower: float
    ci_upper: float
    sample_count: int
    raw_diffs: tuple[float, ...]


@dataclass(frozen=True)
class BenchmarkComparisonResult:
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
    def benchmark_comparison_pass(self) -> bool:
        return self.f2_pass and self.f3_pass and self.f4_pass and self.f5_pass and self.f6_pass


@dataclass(frozen=True)
class BenchmarkGateResult:
    manifest_hash: str
    manifest_sequence_count: int
    manifest_min_step_count: int
    manifest_max_step_count: int
    comparison_result: BenchmarkComparisonResult
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
    def benchmark_gate_pass(self) -> bool:
        return (
            self.f1_pass
            and self.f2_pass
            and self.f3_pass
            and self.f4_pass
            and self.f5_pass
            and self.f6_pass
            and self.f7_pass
        )


def evaluate_benchmark_comparison(*, repeat_count: int = 3) -> BenchmarkComparisonResult:
    """Run the current MIND system against the three frozen baselines."""

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
    return BenchmarkComparisonResult(
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


def evaluate_benchmark_baseline_comparison(
    *,
    baseline_system_id: str,
    repeat_count: int = 3,
    families: tuple[str, ...] | None = None,
    sequence_ids: tuple[str, ...] | None = None,
) -> ComparisonInterval:
    """Compare MIND against one frozen baseline."""

    sequences, manifest = _benchmark_sequences_and_manifest(families, sequence_ids)
    runner = LongHorizonBenchmarkRunner(sequences=sequences, manifest=manifest)
    mind_system = MindLongHorizonSystem()
    baseline_system = _build_baseline_system(baseline_system_id)
    try:
        suite_report = build_benchmark_suite_report(
            runs_by_system={
                "mind": runner.run_many(
                    system_id="mind",
                    system=mind_system,
                    repeat_count=repeat_count,
                ),
                baseline_system_id: runner.run_many(
                    system_id=baseline_system_id,
                    system=baseline_system,
                    repeat_count=repeat_count,
                ),
            }
        )
    finally:
        mind_system.close()

    report_by_system = {report.system_id: report for report in suite_report.system_reports}
    return _comparison_interval(
        report_by_system["mind"].pus.raw_values,
        report_by_system[baseline_system_id].pus.raw_values,
    )


def evaluate_benchmark_baseline_run_comparison(
    *,
    baseline_system_id: str,
    run_id: int = 1,
    families: tuple[str, ...] | None = None,
    sequence_ids: tuple[str, ...] | None = None,
) -> ComparisonInterval:
    """Compare MIND against one frozen baseline for a single benchmark run."""

    sequences, manifest = _benchmark_sequences_and_manifest(families, sequence_ids)
    runner = LongHorizonBenchmarkRunner(sequences=sequences, manifest=manifest)
    mind_system = MindLongHorizonSystem()
    baseline_system = _build_baseline_system(baseline_system_id)
    try:
        mind_run = runner.run_once(system_id="mind", system=mind_system, run_id=run_id)
        baseline_run = runner.run_once(
            system_id=baseline_system_id,
            system=baseline_system,
            run_id=run_id,
        )
    finally:
        mind_system.close()

    return _comparison_interval((mind_run.average_pus,), (baseline_run.average_pus,))


def assert_benchmark_comparison(result: BenchmarkComparisonResult) -> None:
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
            f"F-6 failed: MIND vs plain RAG (mean_diff={result.versus_plain_rag.mean_diff:.4f})"
        )


def evaluate_benchmark_gate(*, repeat_count: int = 3) -> BenchmarkGateResult:
    """Run the full local benchmark gate, including F-7 ablations."""

    manifest = build_long_horizon_eval_manifest_v1()
    comparison_result = evaluate_benchmark_comparison(repeat_count=repeat_count)
    workspace_ablation = evaluate_workspace_ablation(repeat_count=repeat_count)
    offline_maintenance_ablation = evaluate_offline_maintenance_ablation(repeat_count=repeat_count)
    return build_benchmark_gate_result(
        manifest_hash=manifest.fixture_hash,
        manifest_sequence_count=manifest.sequence_count,
        manifest_min_step_count=manifest.min_step_count,
        manifest_max_step_count=manifest.max_step_count,
        comparison_result=comparison_result,
        workspace_ablation=workspace_ablation,
        offline_maintenance_ablation=offline_maintenance_ablation,
    )


def evaluate_workspace_ablation(
    *,
    repeat_count: int = 3,
    families: tuple[str, ...] | None = None,
    sequence_ids: tuple[str, ...] | None = None,
) -> ComparisonInterval:
    """Measure the workspace component ablation against the full MIND system."""

    return _evaluate_component_ablation(
        system_id="mind_without_workspace",
        build_system=lambda: MindLongHorizonSystem(use_workspace=False),
        families=families,
        sequence_ids=sequence_ids,
        repeat_count=repeat_count,
    )


def evaluate_workspace_ablation_run(
    *,
    run_id: int = 1,
    families: tuple[str, ...] | None = None,
    sequence_ids: tuple[str, ...] | None = None,
) -> ComparisonInterval:
    """Measure the workspace ablation against the full MIND system for one run."""

    return _evaluate_component_ablation_run(
        system_id="mind_without_workspace",
        build_system=lambda: MindLongHorizonSystem(use_workspace=False),
        families=families,
        sequence_ids=sequence_ids,
        run_id=run_id,
    )


def evaluate_offline_maintenance_ablation(
    *,
    repeat_count: int = 3,
    families: tuple[str, ...] | None = None,
    sequence_ids: tuple[str, ...] | None = None,
) -> ComparisonInterval:
    """Measure the offline-maintenance ablation against the full MIND system."""

    return _evaluate_component_ablation(
        system_id="mind_without_offline_maintenance",
        build_system=lambda: MindLongHorizonSystem(use_offline_maintenance=False),
        families=families,
        sequence_ids=sequence_ids,
        repeat_count=repeat_count,
    )


def evaluate_offline_maintenance_ablation_run(
    *,
    run_id: int = 1,
    families: tuple[str, ...] | None = None,
    sequence_ids: tuple[str, ...] | None = None,
) -> ComparisonInterval:
    """Measure the offline-maintenance ablation against the full MIND system for one run."""

    return _evaluate_component_ablation_run(
        system_id="mind_without_offline_maintenance",
        build_system=lambda: MindLongHorizonSystem(use_offline_maintenance=False),
        families=families,
        sequence_ids=sequence_ids,
        run_id=run_id,
    )


def build_benchmark_gate_result(
    *,
    manifest_hash: str,
    manifest_sequence_count: int,
    manifest_min_step_count: int,
    manifest_max_step_count: int,
    comparison_result: BenchmarkComparisonResult,
    workspace_ablation: ComparisonInterval,
    offline_maintenance_ablation: ComparisonInterval,
) -> BenchmarkGateResult:
    """Assemble a phase-F benchmark gate result from its components."""

    return BenchmarkGateResult(
        manifest_hash=manifest_hash,
        manifest_sequence_count=manifest_sequence_count,
        manifest_min_step_count=manifest_min_step_count,
        manifest_max_step_count=manifest_max_step_count,
        comparison_result=comparison_result,
        workspace_ablation=workspace_ablation,
        offline_maintenance_ablation=offline_maintenance_ablation,
    )


def assert_benchmark_gate(result: BenchmarkGateResult) -> None:
    if not result.f1_pass:
        raise RuntimeError(
            "F-1 failed: LongHorizonEval manifest invalid "
            f"(sequence_count={result.manifest_sequence_count}, "
            f"step_range={result.manifest_min_step_count}..{result.manifest_max_step_count})"
        )
    assert_benchmark_comparison(result.comparison_result)
    if not result.f7_pass:
        raise RuntimeError(
            "F-7 failed: component ablation did not drop enough PUS "
            f"(workspace_drop={result.workspace_ablation.mean_diff:.4f}, "
            f"offline_drop={result.offline_maintenance_ablation.mean_diff:.4f})"
        )


def write_benchmark_comparison_report_json(
    path: str | Path,
    result: BenchmarkComparisonResult,
) -> Path:
    """Persist the benchmark comparison result as JSON."""

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
        "benchmark_comparison_pass": result.benchmark_comparison_pass,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def write_benchmark_gate_report_json(
    path: str | Path,
    result: BenchmarkGateResult,
) -> Path:
    """Persist the full benchmark gate result as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "benchmark_gate_report_v1",
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
        "benchmark_gate_pass": result.benchmark_gate_pass,
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


def _build_baseline_system(
    baseline_system_id: str,
) -> NoMemoryBaselineSystem | FixedSummaryMemoryBaselineSystem | PlainRagBaselineSystem:
    if baseline_system_id == "no_memory":
        return NoMemoryBaselineSystem()
    if baseline_system_id == "fixed_summary_memory":
        return FixedSummaryMemoryBaselineSystem()
    if baseline_system_id == "plain_rag":
        return PlainRagBaselineSystem()
    raise ValueError(f"unsupported baseline_system_id: {baseline_system_id}")


def _evaluate_component_ablation(
    *,
    system_id: str,
    build_system: Any,
    families: tuple[str, ...] | None,
    sequence_ids: tuple[str, ...] | None,
    repeat_count: int,
) -> ComparisonInterval:
    sequences, manifest = _benchmark_sequences_and_manifest(families, sequence_ids)
    runner = LongHorizonBenchmarkRunner(sequences=sequences, manifest=manifest)
    full_mind_system = MindLongHorizonSystem()
    ablation_system = build_system()
    try:
        full_mind_runs = runner.run_many(
            system_id="mind",
            system=full_mind_system,
            repeat_count=repeat_count,
        )
        ablation_runs = runner.run_many(
            system_id=system_id,
            system=ablation_system,
            repeat_count=repeat_count,
        )
    finally:
        full_mind_system.close()
        ablation_system.close()
    return _comparison_interval(
        tuple(run.average_pus for run in full_mind_runs),
        tuple(run.average_pus for run in ablation_runs),
    )


def _evaluate_component_ablation_run(
    *,
    system_id: str,
    build_system: Any,
    families: tuple[str, ...] | None,
    sequence_ids: tuple[str, ...] | None,
    run_id: int,
) -> ComparisonInterval:
    sequences, manifest = _benchmark_sequences_and_manifest(families, sequence_ids)
    runner = LongHorizonBenchmarkRunner(sequences=sequences, manifest=manifest)
    full_mind_system = MindLongHorizonSystem()
    ablation_system = build_system()
    try:
        full_mind_run = runner.run_once(system_id="mind", system=full_mind_system, run_id=run_id)
        ablation_run = runner.run_once(
            system_id=system_id,
            system=ablation_system,
            run_id=run_id,
        )
    finally:
        full_mind_system.close()
        ablation_system.close()
    return _comparison_interval((full_mind_run.average_pus,), (ablation_run.average_pus,))


def _benchmark_sequences_and_manifest(
    families: tuple[str, ...] | None,
    sequence_ids: tuple[str, ...] | None = None,
) -> tuple[tuple[LongHorizonEvalSequence, ...], LongHorizonEvalManifest]:
    manifest = build_long_horizon_eval_manifest_v1()
    allowed_families = set(families or ())
    allowed_sequence_ids = set(sequence_ids or ())
    sequences = tuple(
        sequence
        for sequence in build_long_horizon_eval_v1()
        if (not allowed_families or sequence.family in allowed_families)
        and (not allowed_sequence_ids or sequence.sequence_id in allowed_sequence_ids)
    )
    if not sequences:
        if allowed_sequence_ids:
            raise ValueError("sequence_ids filter removed all benchmark sequences")
        raise ValueError("families filter removed all benchmark sequences")
    if allowed_families or allowed_sequence_ids:
        manifest = _filtered_manifest(manifest, sequences)
    return sequences, manifest


def _filtered_manifest(
    manifest: LongHorizonEvalManifest,
    sequences: tuple[LongHorizonEvalSequence, ...],
) -> LongHorizonEvalManifest:
    family_counts = Counter(sequence.family for sequence in sequences)
    step_counts = [len(sequence.steps) for sequence in sequences]
    return LongHorizonEvalManifest(
        fixture_name=manifest.fixture_name,
        fixture_hash=manifest.fixture_hash,
        sequence_count=len(sequences),
        min_step_count=min(step_counts),
        max_step_count=max(step_counts),
        family_counts=tuple(sorted(family_counts.items())),
    )
