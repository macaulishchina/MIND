"""Product transport audit report I/O and rendering helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SCHEMA_VERSION = "product_transport_audit_v1"


def write_product_transport_audit_json(
    path: str | Path,
    report: Any,
) -> Path:
    """Persist the full product transport audit report as JSON."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_report_to_dict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def render_product_transport_audit_markdown(
    report: Any,
    *,
    title: str = "Product Transport Audit Report",
) -> str:
    """Render the product transport audit report as Markdown."""
    lines = [
        f"# {title}",
        "",
        f"- Generated at: `{report.generated_at}`",
        f"- Bench version: `{report.bench_version}`",
        f"- Status: `{'PASS' if report.passed else 'FAIL'}`",
        f"- Coverage: `{report.passed_count}/{report.scenario_count}` "
        f"(`{report.coverage:.4f}`)",
        f"- REST/MCP pass rate: "
        f"`{report.rest_mcp_match_count}/{report.rest_mcp_pair_count}` "
        f"(`{report.rest_mcp_pass_rate:.4f}`)",
        f"- REST/CLI pass rate: "
        f"`{report.rest_cli_match_count}/{report.rest_cli_pair_count}` "
        f"(`{report.rest_cli_pass_rate:.4f}`)",
        "",
        "| Scenario | Command Family | REST | MCP | CLI "
        "| REST/MCP | REST/CLI | Failure Reasons |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in report.scenario_results:
        lines.append(
            "| "
            f"{result.scenario_id} | "
            f"{result.command_family} | "
            f"{_markdown_bool(result.rest_available)} | "
            f"{_markdown_bool(result.mcp_available)} | "
            f"{_markdown_bool(result.cli_available)} | "
            f"{_markdown_bool(result.rest_mcp_match)} | "
            f"{_markdown_bool(result.rest_cli_match)} | "
            f"{','.join(result.failure_reasons) if result.failure_reasons else '-'} |"
        )
    if report.failure_ids:
        lines.extend(
            [
                "",
                f"Failing scenarios: `{','.join(report.failure_ids)}`",
            ]
        )
    return "\n".join(lines) + "\n"


def write_product_transport_audit_markdown(
    path: str | Path,
    report: Any,
    *,
    title: str = "Product Transport Audit Report",
) -> Path:
    """Persist the product transport audit report as Markdown."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_product_transport_audit_markdown(report, title=title),
        encoding="utf-8",
    )
    return output_path


def read_product_transport_audit_json(path: str | Path) -> Any:
    """Load a previously persisted product transport audit report."""
    from .product_transport_audit import ProductTransportAuditReport

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError(
            f"unexpected product transport audit schema_version "
            f"({payload.get('schema_version')!r})"
        )
    return _report_from_dict(payload, ProductTransportAuditReport)


def _report_to_dict(report: Any) -> dict[str, Any]:
    return {
        "schema_version": report.schema_version,
        "generated_at": report.generated_at,
        "bench_version": report.bench_version,
        "scenario_count": report.scenario_count,
        "passed_count": report.passed_count,
        "coverage": report.coverage,
        "passed": report.passed,
        "rest_mcp_pair_count": report.rest_mcp_pair_count,
        "rest_mcp_match_count": report.rest_mcp_match_count,
        "rest_mcp_pass_rate": report.rest_mcp_pass_rate,
        "rest_cli_pair_count": report.rest_cli_pair_count,
        "rest_cli_match_count": report.rest_cli_match_count,
        "rest_cli_pass_rate": report.rest_cli_pass_rate,
        "failure_ids": list(report.failure_ids),
        "scenario_results": [
            {
                "scenario_id": result.scenario_id,
                "command_family": result.command_family,
                "rest_available": result.rest_available,
                "mcp_available": result.mcp_available,
                "cli_available": result.cli_available,
                "rest_mcp_match": result.rest_mcp_match,
                "rest_cli_match": result.rest_cli_match,
                "failure_reasons": list(result.failure_reasons),
                "passed": result.passed,
            }
            for result in report.scenario_results
        ],
    }


def _report_from_dict(payload: dict[str, Any], report_cls: type) -> Any:
    from .product_transport_audit import ProductTransportScenarioAuditResult

    return report_cls(
        schema_version=str(payload["schema_version"]),
        generated_at=str(payload["generated_at"]),
        bench_version=str(payload["bench_version"]),
        scenario_count=int(payload["scenario_count"]),
        passed_count=int(payload["passed_count"]),
        rest_mcp_pair_count=int(payload["rest_mcp_pair_count"]),
        rest_mcp_match_count=int(payload["rest_mcp_match_count"]),
        rest_cli_pair_count=int(payload["rest_cli_pair_count"]),
        rest_cli_match_count=int(payload["rest_cli_match_count"]),
        failure_ids=tuple(payload["failure_ids"]),
        scenario_results=tuple(
            ProductTransportScenarioAuditResult(
                scenario_id=str(result["scenario_id"]),
                command_family=str(result["command_family"]),
                rest_available=bool(result["rest_available"]),
                mcp_available=(
                    bool(result["mcp_available"])
                    if result["mcp_available"] is not None
                    else None
                ),
                cli_available=(
                    bool(result["cli_available"])
                    if result["cli_available"] is not None
                    else None
                ),
                rest_mcp_match=(
                    bool(result["rest_mcp_match"])
                    if result["rest_mcp_match"] is not None
                    else None
                ),
                rest_cli_match=(
                    bool(result["rest_cli_match"])
                    if result["rest_cli_match"] is not None
                    else None
                ),
                failure_reasons=tuple(result["failure_reasons"]),
            )
            for result in payload["scenario_results"]
        ),
    )


def _markdown_bool(value: bool | None) -> str:
    if value is None:
        return "-"
    return "PASS" if value else "FAIL"
