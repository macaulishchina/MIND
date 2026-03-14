"""Phase L formal gate helpers."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .audit import (
    TelemetryCoverageAuditResult,
    TelemetryDebugFieldAuditResult,
    TelemetryStateDeltaAuditResult,
    TelemetryTimelineAuditResult,
    TelemetryTraceAuditResult,
    evaluate_telemetry_coverage_audit,
    evaluate_telemetry_debug_field_audit,
    evaluate_telemetry_state_delta_audit,
    evaluate_telemetry_timeline_audit,
    evaluate_telemetry_trace_audit,
)
from .contracts import TelemetryEvent

_SCHEMA_VERSION = "telemetry_gate_report_v1"


@dataclass(frozen=True)
class TelemetryToggleScenarioResult:
    scenario_id: str
    matched: bool


@dataclass(frozen=True)
class TelemetryToggleAuditResult:
    disabled_event_count: int
    scenario_count: int
    matching_scenario_count: int
    drift_scenario_ids: tuple[str, ...]
    scenario_results: tuple[TelemetryToggleScenarioResult, ...]

    @property
    def passed(self) -> bool:
        return (
            self.disabled_event_count == 0 and self.matching_scenario_count == self.scenario_count
        )


@dataclass(frozen=True)
class TelemetryGateResult:
    coverage_audit: TelemetryCoverageAuditResult
    state_delta_audit: TelemetryStateDeltaAuditResult
    trace_audit: TelemetryTraceAuditResult
    toggle_audit: TelemetryToggleAuditResult
    timeline_audit: TelemetryTimelineAuditResult
    debug_field_audit: TelemetryDebugFieldAuditResult

    @property
    def l1_pass(self) -> bool:
        return self.coverage_audit.passed

    @property
    def l2_pass(self) -> bool:
        return self.state_delta_audit.passed

    @property
    def l3_pass(self) -> bool:
        return self.trace_audit.passed

    @property
    def l4_pass(self) -> bool:
        return self.toggle_audit.passed

    @property
    def l5_pass(self) -> bool:
        return self.timeline_audit.passed

    @property
    def l6_pass(self) -> bool:
        return self.debug_field_audit.passed

    @property
    def telemetry_gate_pass(self) -> bool:
        return (
            self.l1_pass
            and self.l2_pass
            and self.l3_pass
            and self.l4_pass
            and self.l5_pass
            and self.l6_pass
        )


def evaluate_telemetry_toggle_audit(
    *,
    disabled_events: Sequence[TelemetryEvent],
    comparisons: Sequence[tuple[str, Any, Any]],
) -> TelemetryToggleAuditResult:
    """Audit that dev_mode off emits no telemetry and preserves behavior."""

    scenario_results: list[TelemetryToggleScenarioResult] = []
    drift_scenario_ids: list[str] = []

    for scenario_id, enabled_result, disabled_result in comparisons:
        matched = _normalize_result(enabled_result) == _normalize_result(disabled_result)
        if not matched:
            drift_scenario_ids.append(scenario_id)
        scenario_results.append(
            TelemetryToggleScenarioResult(
                scenario_id=scenario_id,
                matched=matched,
            )
        )

    matching_scenario_count = sum(result.matched for result in scenario_results)
    return TelemetryToggleAuditResult(
        disabled_event_count=len(tuple(disabled_events)),
        scenario_count=len(scenario_results),
        matching_scenario_count=matching_scenario_count,
        drift_scenario_ids=tuple(drift_scenario_ids),
        scenario_results=tuple(scenario_results),
    )


def evaluate_telemetry_gate(
    events: Sequence[TelemetryEvent],
    *,
    toggle_audit: TelemetryToggleAuditResult,
) -> TelemetryGateResult:
    """Aggregate Phase L telemetry audits into a formal gate result."""

    event_stream = tuple(events)
    return TelemetryGateResult(
        coverage_audit=evaluate_telemetry_coverage_audit(event_stream),
        state_delta_audit=evaluate_telemetry_state_delta_audit(event_stream),
        trace_audit=evaluate_telemetry_trace_audit(event_stream),
        toggle_audit=toggle_audit,
        timeline_audit=evaluate_telemetry_timeline_audit(event_stream),
        debug_field_audit=evaluate_telemetry_debug_field_audit(event_stream),
    )


def assert_telemetry_gate(result: TelemetryGateResult) -> None:
    if not result.l1_pass:
        raise RuntimeError("L-1 failed: telemetry surface coverage is incomplete")
    if not result.l2_pass:
        raise RuntimeError("L-2 failed: state delta completeness regressed")
    if not result.l3_pass:
        raise RuntimeError("L-3 failed: trace correlation chain is incomplete")
    if not result.l4_pass:
        raise RuntimeError("L-4 failed: dev-mode toggle isolation regressed")
    if not result.l5_pass:
        raise RuntimeError("L-5 failed: replayable timeline completeness regressed")
    if not result.l6_pass:
        raise RuntimeError("L-6 failed: debug-field completeness regressed")


def write_telemetry_gate_report_json(
    path: str | Path,
    result: TelemetryGateResult,
    *,
    generated_at: datetime | None = None,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_report_payload(result, generated_at=generated_at), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return output_path


def read_telemetry_gate_report_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError(
            f"unexpected telemetry gate report schema_version ({payload.get('schema_version')!r})"
        )
    return payload


def _report_payload(
    result: TelemetryGateResult,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": (generated_at or datetime.now(UTC)).isoformat(),
        "telemetry_gate_pass": result.telemetry_gate_pass,
        "l1_pass": result.l1_pass,
        "l2_pass": result.l2_pass,
        "l3_pass": result.l3_pass,
        "l4_pass": result.l4_pass,
        "l5_pass": result.l5_pass,
        "l6_pass": result.l6_pass,
        "coverage_audit": {
            "expected_scope_count": result.coverage_audit.expected_scope_count,
            "observed_scope_count": result.coverage_audit.observed_scope_count,
            "coverage": result.coverage_audit.coverage,
            "missing_scopes": [scope.value for scope in result.coverage_audit.missing_scopes],
        },
        "state_delta_audit": {
            "audited_event_count": result.state_delta_audit.audited_event_count,
            "complete_event_count": result.state_delta_audit.complete_event_count,
            "coverage": result.state_delta_audit.coverage,
            "incomplete_event_ids": list(result.state_delta_audit.incomplete_event_ids),
        },
        "trace_audit": {
            "audited_event_count": result.trace_audit.audited_event_count,
            "complete_event_count": result.trace_audit.complete_event_count,
            "coverage": result.trace_audit.coverage,
            "missing_run_id_count": result.trace_audit.missing_run_id_count,
            "missing_operation_id_count": result.trace_audit.missing_operation_id_count,
            "missing_job_id_count": result.trace_audit.missing_job_id_count,
            "missing_workspace_id_count": result.trace_audit.missing_workspace_id_count,
            "missing_object_version_count": result.trace_audit.missing_object_version_count,
            "missing_parent_event_count": result.trace_audit.missing_parent_event_count,
            "out_of_order_parent_event_count": result.trace_audit.out_of_order_parent_event_count,
        },
        "toggle_audit": {
            "disabled_event_count": result.toggle_audit.disabled_event_count,
            "scenario_count": result.toggle_audit.scenario_count,
            "matching_scenario_count": result.toggle_audit.matching_scenario_count,
            "drift_scenario_ids": list(result.toggle_audit.drift_scenario_ids),
            "scenario_results": [
                {
                    "scenario_id": scenario.scenario_id,
                    "matched": scenario.matched,
                }
                for scenario in result.toggle_audit.scenario_results
            ],
        },
        "timeline_audit": {
            "audited_run_count": result.timeline_audit.audited_run_count,
            "replayable_run_count": result.timeline_audit.replayable_run_count,
            "replayable_ratio": result.timeline_audit.replayable_ratio,
        },
        "debug_field_audit": {
            "audited_rule_count": result.debug_field_audit.audited_rule_count,
            "applicable_rule_count": result.debug_field_audit.applicable_rule_count,
            "audited_event_count": result.debug_field_audit.audited_event_count,
            "complete_event_count": result.debug_field_audit.complete_event_count,
            "coverage": result.debug_field_audit.coverage,
            "rule_results": [
                {
                    "rule_id": rule.rule_id,
                    "matched_event_count": rule.matched_event_count,
                    "complete_event_count": rule.complete_event_count,
                    "incomplete_event_ids": list(rule.incomplete_event_ids),
                }
                for rule in result.debug_field_audit.rule_results
            ],
        },
    }


def _normalize_result(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize_result(asdict(value))
    if isinstance(value, dict):
        return {str(key): _normalize_result(item) for key, item in sorted(value.items())}
    if isinstance(value, list | tuple):
        return [_normalize_result(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)
