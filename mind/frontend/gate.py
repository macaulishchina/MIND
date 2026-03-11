"""Formal gate helpers for Phase M frontend experience."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from mind.kernel.store import SQLiteMemoryStore
from mind.primitives.contracts import PrimitiveExecutionContext
from mind.primitives.service import PrimitiveService
from mind.telemetry import InMemoryTelemetryRecorder

from .audit import FrontendResponsiveAuditResult, evaluate_frontend_responsive_audit
from .reporting import FrontendFlowReport, evaluate_frontend_flow_report

_SCHEMA_VERSION = "frontend_gate_report_v1"
_FIXED_TIMESTAMP = datetime(2026, 3, 11, 23, 0, tzinfo=UTC)


@dataclass(frozen=True)
class FrontendDevModeScenarioResult:
    """One dev-mode isolation check for the frontend debug surface."""

    scenario_id: str
    passed: bool


@dataclass(frozen=True)
class FrontendDevModeAuditResult:
    """Aggregate dev-mode isolation result for Phase M."""

    scenario_count: int
    passed_count: int
    failure_ids: tuple[str, ...]
    scenario_results: tuple[FrontendDevModeScenarioResult, ...]

    @property
    def coverage(self) -> float:
        if self.scenario_count == 0:
            return 0.0
        return round(self.passed_count / float(self.scenario_count), 4)

    @property
    def passed(self) -> bool:
        return self.passed_count == self.scenario_count


@dataclass(frozen=True)
class FrontendGateResult:
    """Formal gate result for the lightweight frontend experience layer."""

    flow_report: FrontendFlowReport
    responsive_audit: FrontendResponsiveAuditResult
    dev_mode_audit: FrontendDevModeAuditResult

    @property
    def m1_pass(self) -> bool:
        return self.flow_report.experience_flow_pass

    @property
    def m2_pass(self) -> bool:
        return self.flow_report.config_audit_pass

    @property
    def m3_pass(self) -> bool:
        return self.flow_report.debug_ui_audit_pass

    @property
    def m4_pass(self) -> bool:
        return self.flow_report.transport_surface_present

    @property
    def m5_pass(self) -> bool:
        return self.responsive_audit.passed

    @property
    def m6_pass(self) -> bool:
        return self.dev_mode_audit.passed

    @property
    def frontend_gate_pass(self) -> bool:
        return (
            self.m1_pass
            and self.m2_pass
            and self.m3_pass
            and self.m4_pass
            and self.m5_pass
            and self.m6_pass
        )


def evaluate_frontend_dev_mode_audit() -> FrontendDevModeAuditResult:
    """Verify that debug timelines are gated by dev-mode while staying functional in dev."""

    from mind.app.services.frontend import FrontendDebugAppService

    recorder = InMemoryTelemetryRecorder()
    with TemporaryDirectory(prefix="mind-phase-m-gate-") as tmpdir:
        with SQLiteMemoryStore(Path(tmpdir) / "frontend_gate.sqlite3") as store:
            primitive = PrimitiveService(
                store,
                clock=lambda: _FIXED_TIMESTAMP,
                telemetry_recorder=recorder,
            )
            primitive.write_raw(
                {
                    "record_kind": "user_message",
                    "content": "phase m gate dev mode seed",
                    "episode_id": "phase-m-gate",
                    "timestamp_order": 1,
                },
                PrimitiveExecutionContext(
                    actor="phase-m-gate",
                    budget_scope_id="phase-m-gate",
                    capabilities=[],
                    dev_mode=True,
                    telemetry_run_id="phase-m-gate-run",
                ),
            )

    service = FrontendDebugAppService(telemetry_source=recorder)
    scenario_results: list[FrontendDevModeScenarioResult] = []

    disabled_passed = False
    try:
        service.query_timeline({"run_id": "phase-m-gate-run"}, dev_mode=False)
    except RuntimeError:
        disabled_passed = True
    scenario_results.append(
        FrontendDevModeScenarioResult(
            scenario_id="debug_guard_disabled",
            passed=disabled_passed,
        )
    )

    enabled = service.query_timeline(
        {"run_id": "phase-m-gate-run", "include_state_deltas": True},
        dev_mode=True,
    )
    scenario_results.append(
        FrontendDevModeScenarioResult(
            scenario_id="debug_guard_enabled",
            passed=enabled.returned_event_count >= 3 and len(enabled.object_deltas) >= 1,
        )
    )

    failure_ids = tuple(result.scenario_id for result in scenario_results if not result.passed)
    return FrontendDevModeAuditResult(
        scenario_count=len(scenario_results),
        passed_count=sum(result.passed for result in scenario_results),
        failure_ids=failure_ids,
        scenario_results=tuple(scenario_results),
    )


def evaluate_frontend_gate(
    frontend_root: str | Path | None = None,
    *,
    generated_at: datetime | None = None,
) -> FrontendGateResult:
    """Aggregate the formal Phase M gate inputs into one result."""

    _ = generated_at
    return FrontendGateResult(
        flow_report=evaluate_frontend_flow_report(frontend_root=frontend_root),
        responsive_audit=evaluate_frontend_responsive_audit(frontend_root),
        dev_mode_audit=evaluate_frontend_dev_mode_audit(),
    )


def assert_frontend_gate(result: FrontendGateResult) -> None:
    if not result.m1_pass:
        raise RuntimeError("M-1 failed: frontend experience flow coverage is incomplete")
    if not result.m2_pass:
        raise RuntimeError("M-2 failed: config surface coverage regressed")
    if not result.m3_pass:
        raise RuntimeError("M-3 failed: debug visualization coverage regressed")
    if not result.m4_pass:
        raise RuntimeError("M-4 failed: frontend transport contract surface regressed")
    if not result.m5_pass:
        raise RuntimeError("M-5 failed: responsive audit regressed")
    if not result.m6_pass:
        raise RuntimeError("M-6 failed: dev-mode isolation regressed")


def write_frontend_gate_report_json(path: str | Path, result: FrontendGateResult) -> Path:
    """Persist the full Phase M gate result as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_report_to_dict(result), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def read_frontend_gate_report_json(path: str | Path) -> dict[str, Any]:
    """Load a previously persisted Phase M gate report."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError(
            "unexpected frontend gate report schema_version "
            f"({payload.get('schema_version')!r})"
        )
    return payload


def _report_to_dict(result: FrontendGateResult) -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": _FIXED_TIMESTAMP.isoformat(),
        "frontend_gate_pass": result.frontend_gate_pass,
        "m1_pass": result.m1_pass,
        "m2_pass": result.m2_pass,
        "m3_pass": result.m3_pass,
        "m4_pass": result.m4_pass,
        "m5_pass": result.m5_pass,
        "m6_pass": result.m6_pass,
        "flow_report": {
            "schema_version": result.flow_report.schema_version,
            "bench_version": result.flow_report.bench_version,
            "scenario_count": result.flow_report.scenario_count,
            "passed_count": result.flow_report.passed_count,
            "coverage": result.flow_report.coverage,
            "experience_flow_pass": result.flow_report.experience_flow_pass,
            "config_audit_pass": result.flow_report.config_audit_pass,
            "debug_ui_audit_pass": result.flow_report.debug_ui_audit_pass,
            "transport_surface_present": result.flow_report.transport_surface_present,
            "dev_mode_guard_pass": result.flow_report.dev_mode_guard_pass,
            "failure_ids": list(result.flow_report.failure_ids),
        },
        "responsive_audit": {
            "scenario_count": result.responsive_audit.scenario_count,
            "passed_count": result.responsive_audit.passed_count,
            "coverage": result.responsive_audit.coverage,
            "desktop_total": result.responsive_audit.desktop_total,
            "desktop_pass_count": result.responsive_audit.desktop_pass_count,
            "mobile_total": result.responsive_audit.mobile_total,
            "mobile_pass_count": result.responsive_audit.mobile_pass_count,
            "failure_ids": list(result.responsive_audit.failure_ids),
        },
        "dev_mode_audit": {
            "scenario_count": result.dev_mode_audit.scenario_count,
            "passed_count": result.dev_mode_audit.passed_count,
            "coverage": result.dev_mode_audit.coverage,
            "failure_ids": list(result.dev_mode_audit.failure_ids),
            "scenario_results": [
                {
                    "scenario_id": scenario.scenario_id,
                    "passed": scenario.passed,
                }
                for scenario in result.dev_mode_audit.scenario_results
            ],
        },
    }
