"""Responsive audit helpers for the lightweight Phase M frontend."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from mind.fixtures import FrontendExperienceScenario, build_frontend_experience_bench_v1

from ._assets import load_frontend_javascript, load_frontend_stylesheets

_SCHEMA_VERSION = "frontend_responsive_audit_v1"
_DEFAULT_FRONTEND_ROOT = Path(__file__).resolve().parents[2] / "frontend"
FRONTEND_ENTRYPOINT_MARKERS: dict[str, dict[str, tuple[str, ...]]] = {
    "ingest": {
        "html": ('id="ingest-form"',),
        "js": ("submitIngest",),
        "css": (),
    },
    "retrieve": {
        "html": ('id="retrieve-form"',),
        "js": ("submitRetrieve",),
        "css": (),
    },
    "access": {
        "html": ('id="access-form"',),
        "js": ("submitAccess",),
        "css": (),
    },
    "offline": {
        "html": ('id="offline-form"',),
        "js": ("submitOffline",),
        "css": (),
    },
    "gate_demo": {
        "html": ('id="gate-demo-panel"',),
        "js": ("loadGateDemo",),
        "css": (),
    },
    "config_backend": {
        "html": ('id="settings-form"', 'id="settings-profile"'),
        "js": ("loadSettings",),
        "css": (),
    },
    "config_provider": {
        "html": ('id="settings-provider"', 'id="settings-tab-general"'),
        "js": ("settingsProvider", "applySettings"),
        "css": (),
    },
    "config_dev_mode": {
        "html": ('id="settings-dev-mode"',),
        "js": ("applySettings",),
        "css": (),
    },
    "config_llm": {
        "html": (
            'id="workspace-settings"',
            'id="settings-tab-llm"',
            'id="settings-panel-llm"',
            'id="llm-protocol-grid"',
            'id="llm-service-form"',
            'id="llm-service-list"',
            'id="llm-service-save"',
        ),
        "js": ("settings-panel-llm", "upsertLlmService", "discoverLlmModels", "activateLlmService"),
        "css": (),
    },
    "debug_timeline": {
        "html": ('id="debug-form"',),
        "js": ("loadDebugTimeline",),
        "css": (),
    },
    "debug_object_delta": {
        "html": (),
        "js": ("内容变化",),
        "css": (),
    },
    "debug_context": {
        "html": (),
        "js": ("选择依据", "参考依据"),
        "css": (),
    },
    "debug_guard": {
        "html": ("需要先开启高级排查",),
        "js": ("loadDebugTimeline",),
        "css": (),
    },
}


@dataclass(frozen=True)
class FrontendResponsiveScenarioResult:
    """One responsive audit result for one frozen frontend scenario."""

    scenario_id: str
    entrypoint: str
    viewport: str
    passed: bool
    missing_markers: tuple[str, ...]


@dataclass(frozen=True)
class FrontendResponsiveAuditResult:
    """Aggregate responsive audit result for the Phase M frontend shell."""

    scenario_count: int
    passed_count: int
    desktop_total: int
    desktop_pass_count: int
    mobile_total: int
    mobile_pass_count: int
    viewport_meta_present: bool
    fluid_shell_present: bool
    responsive_grid_present: bool
    static_shell_present: bool
    failure_ids: tuple[str, ...]
    scenario_results: tuple[FrontendResponsiveScenarioResult, ...]

    @property
    def coverage(self) -> float:
        if self.scenario_count == 0:
            return 0.0
        return round(self.passed_count / float(self.scenario_count), 4)

    @property
    def passed(self) -> bool:
        return (
            self.static_shell_present
            and self.viewport_meta_present
            and self.fluid_shell_present
            and self.responsive_grid_present
            and self.passed_count == self.scenario_count
            and self.desktop_pass_count == self.desktop_total
            and self.mobile_pass_count == self.mobile_total
        )


def evaluate_frontend_responsive_audit(
    frontend_root: str | Path | None = None,
    *,
    scenarios: list[FrontendExperienceScenario] | None = None,
) -> FrontendResponsiveAuditResult:
    """Evaluate desktop/mobile shell coverage for the lightweight frontend."""

    root = Path(frontend_root) if frontend_root is not None else _DEFAULT_FRONTEND_ROOT
    index_html = (root / "index.html").read_text(encoding="utf-8")
    app_js = load_frontend_javascript(root)
    styles_css = load_frontend_stylesheets(root, index_html)

    static_shell_present = (
        'id="app-shell"' in index_html
        and "./app.js" in index_html
        and "./styles/" in index_html
    )
    viewport_meta_present = 'name="viewport"' in index_html and "width=device-width" in index_html
    fluid_shell_present = "width: min(1180px, calc(100vw - 2rem));" in styles_css
    responsive_grid_present = "repeat(auto-fit, minmax(20rem, 1fr))" in styles_css

    frozen_scenarios = scenarios or build_frontend_experience_bench_v1()
    audited_scenarios = [
        scenario
        for scenario in frozen_scenarios
        if scenario.viewport in {"desktop", "mobile"}
    ]
    results: list[FrontendResponsiveScenarioResult] = []
    for scenario in audited_scenarios:
        missing_markers = list(
            _missing_markers(
                scenario.entrypoint,
                index_html=index_html,
                app_js=app_js,
                styles_css=styles_css,
            )
        )
        if scenario.viewport == "mobile":
            if not viewport_meta_present:
                missing_markers.append("viewport-meta")
            if not fluid_shell_present:
                missing_markers.append("fluid-shell")
            if not responsive_grid_present:
                missing_markers.append("responsive-grid")
        results.append(
            FrontendResponsiveScenarioResult(
                scenario_id=scenario.scenario_id,
                entrypoint=scenario.entrypoint,
                viewport=scenario.viewport,
                passed=not missing_markers,
                missing_markers=tuple(missing_markers),
            )
        )

    desktop_results = [result for result in results if result.viewport == "desktop"]
    mobile_results = [result for result in results if result.viewport == "mobile"]
    failure_ids = tuple(result.scenario_id for result in results if not result.passed)
    return FrontendResponsiveAuditResult(
        scenario_count=len(results),
        passed_count=sum(result.passed for result in results),
        desktop_total=len(desktop_results),
        desktop_pass_count=sum(result.passed for result in desktop_results),
        mobile_total=len(mobile_results),
        mobile_pass_count=sum(result.passed for result in mobile_results),
        viewport_meta_present=viewport_meta_present,
        fluid_shell_present=fluid_shell_present,
        responsive_grid_present=responsive_grid_present,
        static_shell_present=static_shell_present,
        failure_ids=failure_ids,
        scenario_results=tuple(results),
    )


def write_frontend_responsive_audit_json(
    path: str | Path,
    result: FrontendResponsiveAuditResult,
    *,
    generated_at: datetime | None = None,
) -> Path:
    """Persist the full responsive audit result as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": (generated_at or datetime.now(UTC)).isoformat(),
        **asdict(result),
        "coverage": result.coverage,
        "passed": result.passed,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def _missing_markers(
    entrypoint: str,
    *,
    index_html: str,
    app_js: str,
    styles_css: str,
) -> tuple[str, ...]:
    markers = FRONTEND_ENTRYPOINT_MARKERS.get(entrypoint)
    if markers is None:
        return (f"unsupported-entrypoint:{entrypoint}",)

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
