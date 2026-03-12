"""Aggregated product readiness report helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .deployment_smoke_suite import evaluate_deployment_smoke_suite
from .product_transport_audit import evaluate_runtime_product_transport_audit_report

_SCHEMA_VERSION = "product_readiness_report_v1"
_REPORT_VERSION = "ProductReadinessReport v1"
_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
_REQUIRED_COMPONENT_IDS = (
    "product_transport",
    "deployment_smoke",
    "frontend_gate",
)


@dataclass(frozen=True)
class ProductReadinessComponentResult:
    """Summary for one product-readiness component."""

    component_id: str
    label: str
    passed: bool
    scenario_count: int
    passed_count: int
    failure_ids: tuple[str, ...]
    detail: str

    @property
    def coverage(self) -> float:
        if self.scenario_count == 0:
            return 0.0
        return round(self.passed_count / float(self.scenario_count), 4)


@dataclass(frozen=True)
class ProductReadinessReport:
    """One aggregated readiness report for current product-facing assets."""

    schema_version: str
    generated_at: str
    report_version: str
    components: tuple[ProductReadinessComponentResult, ...]

    @property
    def component_count(self) -> int:
        return len(self.components)

    @property
    def passed_component_count(self) -> int:
        return sum(1 for component in self.components if component.passed)

    @property
    def failure_ids(self) -> tuple[str, ...]:
        return tuple(component.component_id for component in self.components if not component.passed)

    @property
    def passed(self) -> bool:
        return self.passed_component_count == self.component_count


def evaluate_product_readiness_report(
    repo_root: str | Path | None = None,
    *,
    frontend_root: str | Path | None = None,
    generated_at: datetime | None = None,
) -> ProductReadinessReport:
    """Aggregate product transport, deployment smoke, and frontend gate readiness."""

    from mind.frontend import evaluate_frontend_gate

    root = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    product_transport = evaluate_runtime_product_transport_audit_report()
    deployment_smoke = evaluate_deployment_smoke_suite(
        root,
        runtime_product_transport_report=product_transport,
    )
    frontend_gate = evaluate_frontend_gate(frontend_root=frontend_root)

    components = (
        ProductReadinessComponentResult(
            component_id="product_transport",
            label="Product Transport Audit",
            passed=product_transport.passed,
            scenario_count=product_transport.scenario_count,
            passed_count=product_transport.passed_count,
            failure_ids=product_transport.failure_ids,
            detail=(
                f"coverage:{product_transport.coverage:.4f},"
                f"rest_mcp:{product_transport.rest_mcp_pass_rate:.4f},"
                f"rest_cli:{product_transport.rest_cli_pass_rate:.4f}"
            ),
        ),
        ProductReadinessComponentResult(
            component_id="deployment_smoke",
            label="Deployment Smoke",
            passed=deployment_smoke.passed,
            scenario_count=deployment_smoke.scenario_count,
            passed_count=deployment_smoke.passed_count,
            failure_ids=deployment_smoke.failure_ids,
            detail=f"pass_rate:{deployment_smoke.pass_rate:.4f}",
        ),
        ProductReadinessComponentResult(
            component_id="frontend_gate",
            label="Phase M Frontend Gate",
            passed=frontend_gate.frontend_gate_pass,
            scenario_count=6,
            passed_count=sum(
                (
                    frontend_gate.m1_pass,
                    frontend_gate.m2_pass,
                    frontend_gate.m3_pass,
                    frontend_gate.m4_pass,
                    frontend_gate.m5_pass,
                    frontend_gate.m6_pass,
                )
            ),
            failure_ids=tuple(
                gate_id
                for gate_id, gate_passed in (
                    ("M-1", frontend_gate.m1_pass),
                    ("M-2", frontend_gate.m2_pass),
                    ("M-3", frontend_gate.m3_pass),
                    ("M-4", frontend_gate.m4_pass),
                    ("M-5", frontend_gate.m5_pass),
                    ("M-6", frontend_gate.m6_pass),
                )
                if not gate_passed
            ),
            detail=(
                f"flow:{frontend_gate.flow_report.passed_count}/{frontend_gate.flow_report.scenario_count},"
                f"responsive:{frontend_gate.responsive_audit.passed_count}/{frontend_gate.responsive_audit.scenario_count},"
                f"dev_mode:{frontend_gate.dev_mode_audit.passed_count}/{frontend_gate.dev_mode_audit.scenario_count}"
            ),
        ),
    )
    return ProductReadinessReport(
        schema_version=_SCHEMA_VERSION,
        generated_at=(generated_at or datetime.now(UTC)).isoformat(),
        report_version=_REPORT_VERSION,
        components=components,
    )


def assert_product_readiness_report(
    report: ProductReadinessReport,
    *,
    required_component_ids: tuple[str, ...] = _REQUIRED_COMPONENT_IDS,
) -> None:
    """Assert that all required product readiness components pass."""

    component_map = {component.component_id: component for component in report.components}
    missing = tuple(
        component_id
        for component_id in required_component_ids
        if component_id not in component_map
    )
    if missing:
        raise RuntimeError(
            "product readiness report missing required components: "
            + ",".join(missing)
        )

    failing = tuple(
        component
        for component_id in required_component_ids
        for component in (component_map[component_id],)
        if not component.passed
    )
    if failing:
        raise RuntimeError(
            "product readiness gate failed: "
            + "; ".join(
                f"{component.component_id}[{','.join(component.failure_ids) or 'no_failure_ids'}]"
                for component in failing
            )
        )


def write_product_readiness_report_json(
    path: str | Path,
    report: ProductReadinessReport,
) -> Path:
    """Persist the full product readiness report as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_report_to_dict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def render_product_readiness_report_markdown(
    report: ProductReadinessReport,
    *,
    title: str = "Product Readiness Report",
) -> str:
    """Render the product readiness report as a stable Markdown summary."""

    lines = [
        f"# {title}",
        "",
        f"- Generated at: `{report.generated_at}`",
        f"- Report version: `{report.report_version}`",
        f"- Status: `{'PASS' if report.passed else 'FAIL'}`",
        f"- Components passed: `{report.passed_component_count}/{report.component_count}`",
        "",
        "| Component | Status | Passed | Total | Coverage | Failure IDs | Detail |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for component in report.components:
        failure_ids = ",".join(component.failure_ids) if component.failure_ids else "-"
        lines.append(
            "| "
            f"{component.label} | "
            f"{'PASS' if component.passed else 'FAIL'} | "
            f"{component.passed_count} | "
            f"{component.scenario_count} | "
            f"{component.coverage:.4f} | "
            f"{failure_ids} | "
            f"{component.detail} |"
        )
    if report.failure_ids:
        lines.extend(
            [
                "",
                f"Failing components: `{','.join(report.failure_ids)}`",
            ]
        )
    return "\n".join(lines) + "\n"


def write_product_readiness_report_markdown(
    path: str | Path,
    report: ProductReadinessReport,
    *,
    title: str = "Product Readiness Report",
) -> Path:
    """Persist the product readiness report as Markdown."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_product_readiness_report_markdown(report, title=title),
        encoding="utf-8",
    )
    return output_path


def read_product_readiness_report_json(path: str | Path) -> ProductReadinessReport:
    """Load a previously persisted product readiness report."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError(
            "unexpected product readiness report schema_version "
            f"({payload.get('schema_version')!r})"
        )
    return _report_from_dict(payload)


def _report_to_dict(report: ProductReadinessReport) -> dict[str, Any]:
    return {
        "schema_version": report.schema_version,
        "generated_at": report.generated_at,
        "report_version": report.report_version,
        "component_count": report.component_count,
        "passed_component_count": report.passed_component_count,
        "failure_ids": list(report.failure_ids),
        "passed": report.passed,
        "components": [
            {
                "component_id": component.component_id,
                "label": component.label,
                "passed": component.passed,
                "scenario_count": component.scenario_count,
                "passed_count": component.passed_count,
                "coverage": component.coverage,
                "failure_ids": list(component.failure_ids),
                "detail": component.detail,
            }
            for component in report.components
        ],
    }


def _report_from_dict(payload: dict[str, Any]) -> ProductReadinessReport:
    return ProductReadinessReport(
        schema_version=str(payload["schema_version"]),
        generated_at=str(payload["generated_at"]),
        report_version=str(payload["report_version"]),
        components=tuple(
            ProductReadinessComponentResult(
                component_id=str(component["component_id"]),
                label=str(component["label"]),
                passed=bool(component["passed"]),
                scenario_count=int(component["scenario_count"]),
                passed_count=int(component["passed_count"]),
                failure_ids=tuple(str(item) for item in component.get("failure_ids", [])),
                detail=str(component["detail"]),
            )
            for component in payload.get("components", [])
        ),
    )
