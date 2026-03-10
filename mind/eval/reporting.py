"""Persistence and CI reporting helpers for Phase F benchmark runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ._ci import MetricConfidenceInterval, metric_interval
from .runner import (
    LongHorizonBenchmarkRun,
    LongHorizonEvalSequenceResult,
    LongHorizonScoreCard,
)

_REPORT_SCHEMA_VERSION = "phase_f_benchmark_report_v1"


# MetricConfidenceInterval is re-exported from ._ci for backward compatibility.
# All CI math is consolidated in ._ci to avoid duplication.

# _metric_interval is an alias for the shared implementation.
_metric_interval = metric_interval


@dataclass(frozen=True)
class BenchmarkSystemReport:
    system_id: str
    fixture_name: str
    fixture_hash: str
    repeat_count: int
    task_success_rate: MetricConfidenceInterval
    gold_fact_coverage: MetricConfidenceInterval
    reuse_rate: MetricConfidenceInterval
    context_cost_ratio: MetricConfidenceInterval
    maintenance_cost_ratio: MetricConfidenceInterval
    pollution_rate: MetricConfidenceInterval
    pus: MetricConfidenceInterval
    runs: tuple[LongHorizonBenchmarkRun, ...]


@dataclass(frozen=True)
class BenchmarkSuiteReport:
    schema_version: str
    generated_at: str
    fixture_name: str
    fixture_hash: str
    repeat_count: int
    system_reports: tuple[BenchmarkSystemReport, ...]


def build_benchmark_suite_report(
    *,
    runs_by_system: dict[str, tuple[LongHorizonBenchmarkRun, ...]],
    generated_at: datetime | None = None,
) -> BenchmarkSuiteReport:
    """Build a persisted benchmark report with 95% confidence intervals."""

    if not runs_by_system:
        raise ValueError("runs_by_system must not be empty")

    ordered_system_ids = sorted(runs_by_system)
    first_runs = runs_by_system[ordered_system_ids[0]]
    if not first_runs:
        raise ValueError("each system must provide at least one run")
    fixture_name = first_runs[0].fixture_name
    fixture_hash = first_runs[0].fixture_hash
    repeat_count = len(first_runs)
    if any(len(runs_by_system[system_id]) != repeat_count for system_id in ordered_system_ids):
        raise ValueError("all systems must provide the same repeat_count")
    system_reports = tuple(
        _build_system_report(system_id, runs_by_system[system_id], fixture_name, fixture_hash)
        for system_id in ordered_system_ids
    )
    return BenchmarkSuiteReport(
        schema_version=_REPORT_SCHEMA_VERSION,
        generated_at=(generated_at or datetime.now(UTC)).isoformat(),
        fixture_name=fixture_name,
        fixture_hash=fixture_hash,
        repeat_count=repeat_count,
        system_reports=system_reports,
    )


def write_benchmark_suite_report_json(
    path: str | Path,
    report: BenchmarkSuiteReport,
) -> Path:
    """Persist a benchmark suite report as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_suite_report_to_dict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def read_benchmark_suite_report_json(path: str | Path) -> BenchmarkSuiteReport:
    """Load a persisted benchmark suite report from JSON."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != _REPORT_SCHEMA_VERSION:
        raise ValueError(
            "unexpected benchmark report schema_version "
            f"({payload.get('schema_version')!r})"
        )
    return _suite_report_from_dict(payload)


def _build_system_report(
    system_id: str,
    runs: tuple[LongHorizonBenchmarkRun, ...],
    fixture_name: str,
    fixture_hash: str,
) -> BenchmarkSystemReport:
    if not runs:
        raise ValueError(f"system {system_id!r} has no runs")
    if any(run.system_id != system_id for run in runs):
        raise ValueError(f"system {system_id!r} has mismatched run system ids")
    if any(run.fixture_name != fixture_name for run in runs):
        raise ValueError(f"system {system_id!r} has mismatched fixture names")
    if any(run.fixture_hash != fixture_hash for run in runs):
        raise ValueError(f"system {system_id!r} has mismatched fixture hashes")

    return BenchmarkSystemReport(
        system_id=system_id,
        fixture_name=fixture_name,
        fixture_hash=fixture_hash,
        repeat_count=len(runs),
        task_success_rate=_metric_interval([run.average_task_success_rate for run in runs]),
        gold_fact_coverage=_metric_interval([run.average_gold_fact_coverage for run in runs]),
        reuse_rate=_metric_interval([run.average_reuse_rate for run in runs]),
        context_cost_ratio=_metric_interval([run.average_context_cost_ratio for run in runs]),
        maintenance_cost_ratio=_metric_interval(
            [run.average_maintenance_cost_ratio for run in runs]
        ),
        pollution_rate=_metric_interval([run.average_pollution_rate for run in runs]),
        pus=_metric_interval([run.average_pus for run in runs]),
        runs=runs,
    )


def _suite_report_to_dict(report: BenchmarkSuiteReport) -> dict[str, object]:
    return {
        "schema_version": report.schema_version,
        "generated_at": report.generated_at,
        "fixture_name": report.fixture_name,
        "fixture_hash": report.fixture_hash,
        "repeat_count": report.repeat_count,
        "system_reports": [
            _system_report_to_dict(system_report) for system_report in report.system_reports
        ],
    }


def _suite_report_from_dict(payload: dict[str, Any]) -> BenchmarkSuiteReport:
    return BenchmarkSuiteReport(
        schema_version=str(payload["schema_version"]),
        generated_at=str(payload["generated_at"]),
        fixture_name=str(payload["fixture_name"]),
        fixture_hash=str(payload["fixture_hash"]),
        repeat_count=int(payload["repeat_count"]),
        system_reports=tuple(
            _system_report_from_dict(system_payload)
            for system_payload in payload["system_reports"]
        ),
    )


def _system_report_to_dict(report: BenchmarkSystemReport) -> dict[str, object]:
    return {
        "system_id": report.system_id,
        "fixture_name": report.fixture_name,
        "fixture_hash": report.fixture_hash,
        "repeat_count": report.repeat_count,
        "task_success_rate": _metric_interval_to_dict(report.task_success_rate),
        "gold_fact_coverage": _metric_interval_to_dict(report.gold_fact_coverage),
        "reuse_rate": _metric_interval_to_dict(report.reuse_rate),
        "context_cost_ratio": _metric_interval_to_dict(report.context_cost_ratio),
        "maintenance_cost_ratio": _metric_interval_to_dict(report.maintenance_cost_ratio),
        "pollution_rate": _metric_interval_to_dict(report.pollution_rate),
        "pus": _metric_interval_to_dict(report.pus),
        "runs": [_benchmark_run_to_dict(run) for run in report.runs],
    }


def _system_report_from_dict(payload: dict[str, Any]) -> BenchmarkSystemReport:
    return BenchmarkSystemReport(
        system_id=str(payload["system_id"]),
        fixture_name=str(payload["fixture_name"]),
        fixture_hash=str(payload["fixture_hash"]),
        repeat_count=int(payload["repeat_count"]),
        task_success_rate=_metric_interval_from_dict(payload["task_success_rate"]),
        gold_fact_coverage=_metric_interval_from_dict(payload["gold_fact_coverage"]),
        reuse_rate=_metric_interval_from_dict(payload["reuse_rate"]),
        context_cost_ratio=_metric_interval_from_dict(payload["context_cost_ratio"]),
        maintenance_cost_ratio=_metric_interval_from_dict(payload["maintenance_cost_ratio"]),
        pollution_rate=_metric_interval_from_dict(payload["pollution_rate"]),
        pus=_metric_interval_from_dict(payload["pus"]),
        runs=tuple(_benchmark_run_from_dict(run_payload) for run_payload in payload["runs"]),
    )


def _metric_interval_to_dict(interval: MetricConfidenceInterval) -> dict[str, object]:
    return {
        "mean": interval.mean,
        "ci_lower": interval.ci_lower,
        "ci_upper": interval.ci_upper,
        "sample_count": interval.sample_count,
        "raw_values": list(interval.raw_values),
    }


def _metric_interval_from_dict(payload: dict[str, Any]) -> MetricConfidenceInterval:
    return MetricConfidenceInterval(
        mean=float(payload["mean"]),
        ci_lower=float(payload["ci_lower"]),
        ci_upper=float(payload["ci_upper"]),
        sample_count=int(payload["sample_count"]),
        raw_values=tuple(float(value) for value in payload["raw_values"]),
    )


def _benchmark_run_to_dict(run: LongHorizonBenchmarkRun) -> dict[str, object]:
    return {
        "system_id": run.system_id,
        "run_id": run.run_id,
        "fixture_name": run.fixture_name,
        "fixture_hash": run.fixture_hash,
        "sequence_count": run.sequence_count,
        "average_task_success_rate": run.average_task_success_rate,
        "average_gold_fact_coverage": run.average_gold_fact_coverage,
        "average_reuse_rate": run.average_reuse_rate,
        "average_context_cost_ratio": run.average_context_cost_ratio,
        "average_maintenance_cost_ratio": run.average_maintenance_cost_ratio,
        "average_pollution_rate": run.average_pollution_rate,
        "average_pus": run.average_pus,
        "sequence_results": [
            _sequence_result_to_dict(sequence_result) for sequence_result in run.sequence_results
        ],
    }


def _benchmark_run_from_dict(payload: dict[str, Any]) -> LongHorizonBenchmarkRun:
    return LongHorizonBenchmarkRun(
        system_id=str(payload["system_id"]),
        run_id=int(payload["run_id"]),
        fixture_name=str(payload["fixture_name"]),
        fixture_hash=str(payload["fixture_hash"]),
        sequence_count=int(payload["sequence_count"]),
        average_task_success_rate=float(payload["average_task_success_rate"]),
        average_gold_fact_coverage=float(payload["average_gold_fact_coverage"]),
        average_reuse_rate=float(payload["average_reuse_rate"]),
        average_context_cost_ratio=float(payload["average_context_cost_ratio"]),
        average_maintenance_cost_ratio=float(payload["average_maintenance_cost_ratio"]),
        average_pollution_rate=float(payload["average_pollution_rate"]),
        average_pus=float(payload["average_pus"]),
        sequence_results=tuple(
            _sequence_result_from_dict(sequence_payload)
            for sequence_payload in payload["sequence_results"]
        ),
    )


def _sequence_result_to_dict(sequence_result: LongHorizonEvalSequenceResult) -> dict[str, object]:
    return {
        "sequence_id": sequence_result.sequence_id,
        "family": sequence_result.family,
        "score_card": _score_card_to_dict(sequence_result.score_card),
    }


def _sequence_result_from_dict(payload: dict[str, Any]) -> LongHorizonEvalSequenceResult:
    return LongHorizonEvalSequenceResult(
        sequence_id=str(payload["sequence_id"]),
        family=str(payload["family"]),
        score_card=_score_card_from_dict(payload["score_card"]),
    )


def _score_card_to_dict(score_card: LongHorizonScoreCard) -> dict[str, object]:
    return {
        "task_success_rate": score_card.task_success_rate,
        "gold_fact_coverage": score_card.gold_fact_coverage,
        "reuse_rate": score_card.reuse_rate,
        "context_cost_ratio": score_card.context_cost_ratio,
        "maintenance_cost_ratio": score_card.maintenance_cost_ratio,
        "pollution_rate": score_card.pollution_rate,
        "pus": score_card.pus,
    }


def _score_card_from_dict(payload: dict[str, Any]) -> LongHorizonScoreCard:
    return LongHorizonScoreCard(
        task_success_rate=float(payload["task_success_rate"]),
        gold_fact_coverage=float(payload["gold_fact_coverage"]),
        reuse_rate=float(payload["reuse_rate"]),
        context_cost_ratio=float(payload["context_cost_ratio"]),
        maintenance_cost_ratio=float(payload["maintenance_cost_ratio"]),
        pollution_rate=float(payload["pollution_rate"]),
    )
