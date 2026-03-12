"""Reporting helpers for the lightweight Phase M frontend shell."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mind.fixtures import FrontendExperienceScenario, build_frontend_experience_bench_v1

from .audit import FRONTEND_ENTRYPOINT_MARKERS, evaluate_frontend_responsive_audit

_SCHEMA_VERSION = "frontend_flow_report_v1"
_DEFAULT_FRONTEND_ROOT = Path(__file__).resolve().parents[2] / "frontend"
_REQUIRED_EXPERIENCE_ENTRYPOINTS = (
    "ingest",
    "retrieve",
    "access",
    "offline",
    "gate_demo",
)
_TRANSPORT_MARKERS: dict[str, tuple[str, ...]] = {
    "ingest": ('"/v1/frontend/ingest"', "submitIngest"),
    "retrieve": ('"/v1/frontend/retrieve"', "submitRetrieve"),
    "access": ('"/v1/frontend/access"', "submitAccess"),
    "offline": ('"/v1/frontend/offline"', "submitOffline"),
    "gate_demo": ('"/v1/frontend/gate-demo"', "loadGateDemo"),
    "config_backend": ('"/v1/frontend/settings"', '"/v1/frontend/settings:preview"', "loadSettings"),
    "config_provider": ('"/v1/frontend/settings"', '"/v1/frontend/settings:preview"', "previewSettings"),
    "config_dev_mode": ('"/v1/frontend/settings:apply"', "applySettings"),
    "config_restore": ('"/v1/frontend/settings:restore"', "restoreSettings"),
    "debug_timeline": ('"/v1/frontend/debug:timeline"', "loadDebugTimeline"),
    "debug_object_delta": ('"/v1/frontend/debug:timeline"', "loadDebugTimeline"),
    "debug_context": ('"/v1/frontend/debug:timeline"', "loadDebugTimeline"),
    "debug_guard": ('"/v1/frontend/debug:timeline"', "loadDebugTimeline"),
}


@dataclass(frozen=True)
class FrontendFlowScenarioResult:
    """Flow-level audit result for one frozen frontend scenario."""

    scenario_id: str
    category: str
    entrypoint: str
    viewport: str
    requires_dev_mode: bool
    passed: bool
    missing_checks: tuple[str, ...]


@dataclass(frozen=True)
class FrontendFlowCategorySummary:
    """Aggregate flow summary for one frontend category."""

    category: str
    scenario_count: int
    passed_count: int
    entrypoint_count: int
    failure_ids: tuple[str, ...]

    @property
    def coverage(self) -> float:
        if self.scenario_count == 0:
            return 0.0
        return round(self.passed_count / float(self.scenario_count), 4)

    @property
    def passed(self) -> bool:
        return self.passed_count == self.scenario_count


@dataclass(frozen=True)
class FrontendFlowReport:
    """Formal flow report for the lightweight Phase M frontend shell."""

    schema_version: str
    generated_at: str
    bench_version: str
    scenario_count: int
    passed_count: int
    required_experience_entrypoints: tuple[str, ...]
    covered_experience_entrypoints: tuple[str, ...]
    transport_surface_present: bool
    responsive_audit_pass: bool
    responsive_coverage: float
    experience_flow_pass: bool
    config_audit_pass: bool
    debug_ui_audit_pass: bool
    dev_mode_guard_pass: bool
    failure_ids: tuple[str, ...]
    category_summaries: tuple[FrontendFlowCategorySummary, ...]
    scenario_results: tuple[FrontendFlowScenarioResult, ...]

    @property
    def coverage(self) -> float:
        if self.scenario_count == 0:
            return 0.0
        return round(self.passed_count / float(self.scenario_count), 4)

    @property
    def passed(self) -> bool:
        return (
            self.transport_surface_present
            and self.responsive_audit_pass
            and self.experience_flow_pass
            and self.config_audit_pass
            and self.debug_ui_audit_pass
            and self.dev_mode_guard_pass
            and self.passed_count == self.scenario_count
        )


def evaluate_frontend_flow_report(
    frontend_root: str | Path | None = None,
    *,
    scenarios: list[FrontendExperienceScenario] | None = None,
    generated_at: datetime | None = None,
) -> FrontendFlowReport:
    """Evaluate the frozen Phase M frontend flow surface against current assets."""

    root = Path(frontend_root) if frontend_root is not None else _DEFAULT_FRONTEND_ROOT
    index_html = (root / "index.html").read_text(encoding="utf-8")
    app_js = (root / "app.js").read_text(encoding="utf-8")
    api_js = (root / "api.js").read_text(encoding="utf-8")
    styles_css = (root / "styles.css").read_text(encoding="utf-8")

    frozen_scenarios = scenarios or build_frontend_experience_bench_v1()
    responsive_audit = evaluate_frontend_responsive_audit(root, scenarios=frozen_scenarios)
    responsive_results = {
        result.scenario_id: result for result in responsive_audit.scenario_results
    }

    scenario_results: list[FrontendFlowScenarioResult] = []
    for scenario in frozen_scenarios:
        missing_checks = list(
            _missing_static_markers(
                scenario.entrypoint,
                index_html=index_html,
                app_js=app_js,
                styles_css=styles_css,
            )
        )
        missing_checks.extend(
            _missing_transport_markers(
                scenario.entrypoint,
                api_js=api_js,
            )
        )

        responsive_result = responsive_results.get(scenario.scenario_id)
        if responsive_result is not None and not responsive_result.passed:
            missing_checks.extend(
                f"responsive:{marker}" for marker in responsive_result.missing_markers
            )
        if scenario.entrypoint == "debug_guard" and "需要先开启高级排查" not in index_html:
            missing_checks.append("html:需要先开启高级排查")

        scenario_results.append(
            FrontendFlowScenarioResult(
                scenario_id=scenario.scenario_id,
                category=scenario.category,
                entrypoint=scenario.entrypoint,
                viewport=scenario.viewport,
                requires_dev_mode=scenario.requires_dev_mode,
                passed=not missing_checks,
                missing_checks=tuple(missing_checks),
            )
        )

    category_summaries = tuple(
        _build_category_summary(category, scenario_results)
        for category in ("experience", "config", "debug")
    )
    category_map = {summary.category: summary for summary in category_summaries}
    failure_ids = tuple(result.scenario_id for result in scenario_results if not result.passed)
    transport_surface_present = not any(
        any(check.startswith("transport:") for check in result.missing_checks)
        for result in scenario_results
    )
    covered_experience_entrypoints_set = {
        result.entrypoint
        for result in scenario_results
        if result.category == "experience" and result.passed
    }
    covered_experience_entrypoints = tuple(
        entrypoint
        for entrypoint in _REQUIRED_EXPERIENCE_ENTRYPOINTS
        if entrypoint in covered_experience_entrypoints_set
    )
    debug_guard = next(
        result for result in scenario_results if result.entrypoint == "debug_guard"
    )
    return FrontendFlowReport(
        schema_version=_SCHEMA_VERSION,
        generated_at=(generated_at or datetime.now(UTC)).isoformat(),
        bench_version="FrontendExperienceBench v1",
        scenario_count=len(scenario_results),
        passed_count=sum(result.passed for result in scenario_results),
        required_experience_entrypoints=_REQUIRED_EXPERIENCE_ENTRYPOINTS,
        covered_experience_entrypoints=covered_experience_entrypoints,
        transport_surface_present=transport_surface_present,
        responsive_audit_pass=responsive_audit.passed,
        responsive_coverage=responsive_audit.coverage,
        experience_flow_pass=covered_experience_entrypoints == _REQUIRED_EXPERIENCE_ENTRYPOINTS,
        config_audit_pass=category_map["config"].passed,
        debug_ui_audit_pass=category_map["debug"].passed,
        dev_mode_guard_pass=debug_guard.passed and all(
            result.requires_dev_mode
            for result in scenario_results
            if result.category == "debug"
        ),
        failure_ids=failure_ids,
        category_summaries=category_summaries,
        scenario_results=tuple(scenario_results),
    )


def write_frontend_flow_report_json(path: str | Path, report: FrontendFlowReport) -> Path:
    """Persist the full frontend flow report as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_report_to_dict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def read_frontend_flow_report_json(path: str | Path) -> FrontendFlowReport:
    """Load a previously persisted frontend flow report JSON payload."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError(
            "unexpected frontend flow report schema_version "
            f"({payload.get('schema_version')!r})"
        )
    return _report_from_dict(payload)


def _build_category_summary(
    category: str,
    scenario_results: list[FrontendFlowScenarioResult],
) -> FrontendFlowCategorySummary:
    matching_results = [result for result in scenario_results if result.category == category]
    return FrontendFlowCategorySummary(
        category=category,
        scenario_count=len(matching_results),
        passed_count=sum(result.passed for result in matching_results),
        entrypoint_count=len({result.entrypoint for result in matching_results}),
        failure_ids=tuple(result.scenario_id for result in matching_results if not result.passed),
    )


def _missing_static_markers(
    entrypoint: str,
    *,
    index_html: str,
    app_js: str,
    styles_css: str,
) -> tuple[str, ...]:
    markers = FRONTEND_ENTRYPOINT_MARKERS.get(entrypoint)
    if markers is None:
        return (f"static:unsupported-entrypoint:{entrypoint}",)

    missing: list[str] = []
    for marker in markers["html"]:
        if marker not in index_html:
            missing.append(f"html:{marker}")
    for marker in markers["js"]:
        if marker not in app_js:
            missing.append(f"js:{marker}")
    for marker in markers["css"]:
        if marker not in styles_css:
            missing.append(f"css:{marker}")
    return tuple(missing)


def _missing_transport_markers(
    entrypoint: str,
    *,
    api_js: str,
) -> tuple[str, ...]:
    markers = _TRANSPORT_MARKERS.get(entrypoint)
    if markers is None:
        return (f"transport:unsupported-entrypoint:{entrypoint}",)
    return tuple(
        f"transport:{marker}"
        for marker in markers
        if marker not in api_js
    )


def _report_to_dict(report: FrontendFlowReport) -> dict[str, Any]:
    return {
        "schema_version": report.schema_version,
        "generated_at": report.generated_at,
        "bench_version": report.bench_version,
        "scenario_count": report.scenario_count,
        "passed_count": report.passed_count,
        "coverage": report.coverage,
        "passed": report.passed,
        "required_experience_entrypoints": list(report.required_experience_entrypoints),
        "covered_experience_entrypoints": list(report.covered_experience_entrypoints),
        "transport_surface_present": report.transport_surface_present,
        "responsive_audit_pass": report.responsive_audit_pass,
        "responsive_coverage": report.responsive_coverage,
        "experience_flow_pass": report.experience_flow_pass,
        "config_audit_pass": report.config_audit_pass,
        "debug_ui_audit_pass": report.debug_ui_audit_pass,
        "dev_mode_guard_pass": report.dev_mode_guard_pass,
        "failure_ids": list(report.failure_ids),
        "category_summaries": [
            {
                "category": summary.category,
                "scenario_count": summary.scenario_count,
                "passed_count": summary.passed_count,
                "entrypoint_count": summary.entrypoint_count,
                "coverage": summary.coverage,
                "passed": summary.passed,
                "failure_ids": list(summary.failure_ids),
            }
            for summary in report.category_summaries
        ],
        "scenario_results": [
            {
                "scenario_id": result.scenario_id,
                "category": result.category,
                "entrypoint": result.entrypoint,
                "viewport": result.viewport,
                "requires_dev_mode": result.requires_dev_mode,
                "passed": result.passed,
                "missing_checks": list(result.missing_checks),
            }
            for result in report.scenario_results
        ],
    }


def _report_from_dict(payload: dict[str, Any]) -> FrontendFlowReport:
    return FrontendFlowReport(
        schema_version=str(payload["schema_version"]),
        generated_at=str(payload["generated_at"]),
        bench_version=str(payload["bench_version"]),
        scenario_count=int(payload["scenario_count"]),
        passed_count=int(payload["passed_count"]),
        required_experience_entrypoints=tuple(payload["required_experience_entrypoints"]),
        covered_experience_entrypoints=tuple(payload["covered_experience_entrypoints"]),
        transport_surface_present=bool(payload["transport_surface_present"]),
        responsive_audit_pass=bool(payload["responsive_audit_pass"]),
        responsive_coverage=float(payload["responsive_coverage"]),
        experience_flow_pass=bool(payload["experience_flow_pass"]),
        config_audit_pass=bool(payload["config_audit_pass"]),
        debug_ui_audit_pass=bool(payload["debug_ui_audit_pass"]),
        dev_mode_guard_pass=bool(payload["dev_mode_guard_pass"]),
        failure_ids=tuple(payload["failure_ids"]),
        category_summaries=tuple(
            FrontendFlowCategorySummary(
                category=str(summary["category"]),
                scenario_count=int(summary["scenario_count"]),
                passed_count=int(summary["passed_count"]),
                entrypoint_count=int(summary["entrypoint_count"]),
                failure_ids=tuple(summary["failure_ids"]),
            )
            for summary in payload["category_summaries"]
        ),
        scenario_results=tuple(
            FrontendFlowScenarioResult(
                scenario_id=str(result["scenario_id"]),
                category=str(result["category"]),
                entrypoint=str(result["entrypoint"]),
                viewport=str(result["viewport"]),
                requires_dev_mode=bool(result["requires_dev_mode"]),
                passed=bool(result["passed"]),
                missing_checks=tuple(result["missing_checks"]),
            )
            for result in payload["scenario_results"]
        ),
    )
