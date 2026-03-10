"""Cost accounting helpers for Phase G strategy optimization work."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from mind.fixtures.long_horizon_eval import (
    build_long_horizon_eval_manifest_v1,
    build_long_horizon_eval_v1,
)

from ._ci import MetricConfidenceInterval, metric_interval, t_critical
from .mind_system import MindLongHorizonSystem, MindRunCostSnapshot
from .runner import LongHorizonBenchmarkRun, LongHorizonBenchmarkRunner

_COST_REPORT_SCHEMA_VERSION = "phase_g_cost_report_v1"


@dataclass(frozen=True)
class CostBudgetProfile:
    profile_id: str
    fixture_name: str
    fixture_hash: str
    repeat_count: int
    token_budget_ratio: float
    storage_budget_ratio: float
    maintenance_budget_ratio: float
    total_budget_ratio: float


@dataclass(frozen=True)
class PhaseGCostReport:
    schema_version: str
    generated_at: str
    fixture_name: str
    fixture_hash: str
    system_id: str
    strategy_id: str
    repeat_count: int
    budget_profile: CostBudgetProfile
    token_cost_ratio: MetricConfidenceInterval
    storage_cost_ratio: MetricConfidenceInterval
    maintenance_cost_ratio: MetricConfidenceInterval
    total_cost_ratio: MetricConfidenceInterval
    token_budget_bias: MetricConfidenceInterval
    storage_budget_bias: MetricConfidenceInterval
    maintenance_budget_bias: MetricConfidenceInterval
    total_budget_bias: MetricConfidenceInterval
    snapshots: tuple[MindRunCostSnapshot, ...]


def evaluate_fixed_rule_cost_report(*, repeat_count: int = 3) -> PhaseGCostReport:
    """Run the frozen fixed-rule strategy and persist its budget profile."""

    if repeat_count < 1:
        raise ValueError("repeat_count must be >= 1")

    sequences = build_long_horizon_eval_v1()
    manifest = build_long_horizon_eval_manifest_v1()
    runner = LongHorizonBenchmarkRunner(sequences=sequences, manifest=manifest)
    system = MindLongHorizonSystem()
    try:
        runs = runner.run_many(
            system_id="mind_fixed_rule",
            system=system,
            repeat_count=repeat_count,
        )
        snapshots = tuple(system.cost_snapshot(run.run_id) for run in runs)
    finally:
        system.close()

    budget_profile = build_cost_budget_profile(
        profile_id="phase_g_fixed_rule_budget_v1",
        fixture_name=manifest.fixture_name,
        fixture_hash=manifest.fixture_hash,
        runs=runs,
        snapshots=snapshots,
    )
    return build_phase_g_cost_report(
        system_id="mind_fixed_rule",
        strategy_id=snapshots[0].strategy_id,
        runs=runs,
        snapshots=snapshots,
        budget_profile=budget_profile,
    )


def build_cost_budget_profile(
    *,
    profile_id: str,
    fixture_name: str,
    fixture_hash: str,
    runs: tuple[LongHorizonBenchmarkRun, ...],
    snapshots: tuple[MindRunCostSnapshot, ...],
) -> CostBudgetProfile:
    """Freeze a budget profile from an existing set of runs and cost snapshots."""

    _validate_runs_and_snapshots(
        system_id=runs[0].system_id if runs else "unknown",
        runs=runs,
        snapshots=snapshots,
    )
    return CostBudgetProfile(
        profile_id=profile_id,
        fixture_name=fixture_name,
        fixture_hash=fixture_hash,
        repeat_count=len(runs),
        token_budget_ratio=round(mean(run.average_context_cost_ratio for run in runs), 4),
        storage_budget_ratio=round(mean(snapshot.storage_cost_ratio for snapshot in snapshots), 4),
        maintenance_budget_ratio=round(
            mean(run.average_maintenance_cost_ratio for run in runs),
            4,
        ),
        total_budget_ratio=round(
            mean(
                _total_cost_ratio(run, snapshot)
                for run, snapshot in zip(runs, snapshots, strict=True)
            ),
            4,
        ),
    )


def build_phase_g_cost_report(
    *,
    system_id: str,
    strategy_id: str,
    runs: tuple[LongHorizonBenchmarkRun, ...],
    snapshots: tuple[MindRunCostSnapshot, ...],
    budget_profile: CostBudgetProfile,
    generated_at: datetime | None = None,
) -> PhaseGCostReport:
    """Build a persisted Phase G cost report for a single strategy/system."""

    _validate_runs_and_snapshots(system_id=system_id, runs=runs, snapshots=snapshots)
    if len(runs) != budget_profile.repeat_count:
        raise ValueError(
            "budget profile repeat_count does not match runs "
            f"({budget_profile.repeat_count} != {len(runs)})"
        )
    if any(run.fixture_hash != budget_profile.fixture_hash for run in runs):
        raise ValueError("runs fixture_hash does not match budget profile")

    token_costs = [run.average_context_cost_ratio for run in runs]
    storage_costs = [snapshot.storage_cost_ratio for snapshot in snapshots]
    maintenance_costs = [run.average_maintenance_cost_ratio for run in runs]
    total_costs = [
        _total_cost_ratio(run, snapshot) for run, snapshot in zip(runs, snapshots, strict=True)
    ]
    return PhaseGCostReport(
        schema_version=_COST_REPORT_SCHEMA_VERSION,
        generated_at=(generated_at or datetime.now(UTC)).isoformat(),
        fixture_name=runs[0].fixture_name,
        fixture_hash=runs[0].fixture_hash,
        system_id=system_id,
        strategy_id=strategy_id,
        repeat_count=len(runs),
        budget_profile=budget_profile,
        token_cost_ratio=_metric_interval(token_costs),
        storage_cost_ratio=_metric_interval(storage_costs),
        maintenance_cost_ratio=_metric_interval(maintenance_costs),
        total_cost_ratio=_metric_interval(total_costs),
        token_budget_bias=_metric_interval(
            [_relative_bias(value, budget_profile.token_budget_ratio) for value in token_costs]
        ),
        storage_budget_bias=_metric_interval(
            [_relative_bias(value, budget_profile.storage_budget_ratio) for value in storage_costs]
        ),
        maintenance_budget_bias=_metric_interval(
            [
                _relative_bias(value, budget_profile.maintenance_budget_ratio)
                for value in maintenance_costs
            ]
        ),
        total_budget_bias=_metric_interval(
            [_relative_bias(value, budget_profile.total_budget_ratio) for value in total_costs]
        ),
        snapshots=snapshots,
    )


def write_phase_g_cost_report_json(
    path: str | Path,
    report: PhaseGCostReport,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_cost_report_to_dict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def read_phase_g_cost_report_json(path: str | Path) -> PhaseGCostReport:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != _COST_REPORT_SCHEMA_VERSION:
        raise ValueError(
            "unexpected phase_g cost report schema_version "
            f"({payload.get('schema_version')!r})"
        )
    return _cost_report_from_dict(payload)


def _validate_runs_and_snapshots(
    *,
    system_id: str,
    runs: tuple[LongHorizonBenchmarkRun, ...],
    snapshots: tuple[MindRunCostSnapshot, ...],
) -> None:
    if not runs:
        raise ValueError("runs must not be empty")
    if len(runs) != len(snapshots):
        raise ValueError("runs and snapshots must have the same length")
    if any(run.system_id != system_id for run in runs):
        raise ValueError(f"system {system_id!r} has mismatched run system ids")
    for run, snapshot in zip(runs, snapshots, strict=True):
        if run.run_id != snapshot.run_id:
            raise ValueError(
                "run and snapshot ids do not align "
                f"({run.run_id} != {snapshot.run_id})"
            )


# _metric_interval and _t_critical are aliases for the shared implementations
# consolidated in ._ci to eliminate duplication with reporting.py.
_metric_interval = metric_interval
_t_critical = t_critical


def _relative_bias(actual: float, target: float) -> float:
    if target <= 0.0:
        raise ValueError("budget target must be > 0")
    return round((actual / target) - 1.0, 4)


def _total_cost_ratio(
    run: LongHorizonBenchmarkRun,
    snapshot: MindRunCostSnapshot,
) -> float:
    return round(
        run.average_context_cost_ratio
        + snapshot.storage_cost_ratio
        + run.average_maintenance_cost_ratio,
        4,
    )


def _cost_report_to_dict(report: PhaseGCostReport) -> dict[str, object]:
    return {
        "schema_version": report.schema_version,
        "generated_at": report.generated_at,
        "fixture_name": report.fixture_name,
        "fixture_hash": report.fixture_hash,
        "system_id": report.system_id,
        "strategy_id": report.strategy_id,
        "repeat_count": report.repeat_count,
        "budget_profile": _budget_profile_to_dict(report.budget_profile),
        "token_cost_ratio": _metric_interval_to_dict(report.token_cost_ratio),
        "storage_cost_ratio": _metric_interval_to_dict(report.storage_cost_ratio),
        "maintenance_cost_ratio": _metric_interval_to_dict(report.maintenance_cost_ratio),
        "total_cost_ratio": _metric_interval_to_dict(report.total_cost_ratio),
        "token_budget_bias": _metric_interval_to_dict(report.token_budget_bias),
        "storage_budget_bias": _metric_interval_to_dict(report.storage_budget_bias),
        "maintenance_budget_bias": _metric_interval_to_dict(report.maintenance_budget_bias),
        "total_budget_bias": _metric_interval_to_dict(report.total_budget_bias),
        "snapshots": [_snapshot_to_dict(snapshot) for snapshot in report.snapshots],
    }


def _cost_report_from_dict(payload: dict[str, Any]) -> PhaseGCostReport:
    return PhaseGCostReport(
        schema_version=str(payload["schema_version"]),
        generated_at=str(payload["generated_at"]),
        fixture_name=str(payload["fixture_name"]),
        fixture_hash=str(payload["fixture_hash"]),
        system_id=str(payload["system_id"]),
        strategy_id=str(payload["strategy_id"]),
        repeat_count=int(payload["repeat_count"]),
        budget_profile=_budget_profile_from_dict(payload["budget_profile"]),
        token_cost_ratio=_metric_interval_from_dict(payload["token_cost_ratio"]),
        storage_cost_ratio=_metric_interval_from_dict(payload["storage_cost_ratio"]),
        maintenance_cost_ratio=_metric_interval_from_dict(payload["maintenance_cost_ratio"]),
        total_cost_ratio=_metric_interval_from_dict(payload["total_cost_ratio"]),
        token_budget_bias=_metric_interval_from_dict(payload["token_budget_bias"]),
        storage_budget_bias=_metric_interval_from_dict(payload["storage_budget_bias"]),
        maintenance_budget_bias=_metric_interval_from_dict(payload["maintenance_budget_bias"]),
        total_budget_bias=_metric_interval_from_dict(payload["total_budget_bias"]),
        snapshots=tuple(_snapshot_from_dict(snapshot) for snapshot in payload["snapshots"]),
    )


def _budget_profile_to_dict(profile: CostBudgetProfile) -> dict[str, object]:
    return {
        "profile_id": profile.profile_id,
        "fixture_name": profile.fixture_name,
        "fixture_hash": profile.fixture_hash,
        "repeat_count": profile.repeat_count,
        "token_budget_ratio": profile.token_budget_ratio,
        "storage_budget_ratio": profile.storage_budget_ratio,
        "maintenance_budget_ratio": profile.maintenance_budget_ratio,
        "total_budget_ratio": profile.total_budget_ratio,
    }


def _budget_profile_from_dict(payload: dict[str, Any]) -> CostBudgetProfile:
    return CostBudgetProfile(
        profile_id=str(payload["profile_id"]),
        fixture_name=str(payload["fixture_name"]),
        fixture_hash=str(payload["fixture_hash"]),
        repeat_count=int(payload["repeat_count"]),
        token_budget_ratio=float(payload["token_budget_ratio"]),
        storage_budget_ratio=float(payload["storage_budget_ratio"]),
        maintenance_budget_ratio=float(payload["maintenance_budget_ratio"]),
        total_budget_ratio=float(payload["total_budget_ratio"]),
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


def _snapshot_to_dict(snapshot: MindRunCostSnapshot) -> dict[str, object]:
    return {
        "run_id": snapshot.run_id,
        "strategy_id": snapshot.strategy_id,
        "base_object_count": snapshot.base_object_count,
        "generated_schema_count": snapshot.generated_schema_count,
        "total_object_count": snapshot.total_object_count,
        "storage_cost_ratio": snapshot.storage_cost_ratio,
    }


def _snapshot_from_dict(payload: dict[str, Any]) -> MindRunCostSnapshot:
    return MindRunCostSnapshot(
        run_id=int(payload["run_id"]),
        strategy_id=str(payload["strategy_id"]),
        base_object_count=int(payload["base_object_count"]),
        generated_schema_count=int(payload["generated_schema_count"]),
        total_object_count=int(payload["total_object_count"]),
        storage_cost_ratio=float(payload["storage_cost_ratio"]),
    )
