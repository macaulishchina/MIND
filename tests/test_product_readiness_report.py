from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mind.cli import product_readiness_gate_main, product_readiness_report_main
from mind.fixtures import (
    ProductReadinessComponentResult,
    ProductReadinessReport,
    assert_product_readiness_report,
    evaluate_product_readiness_report,
    read_product_readiness_report_json,
    render_product_readiness_report_markdown,
    write_product_readiness_report_json,
    write_product_readiness_report_markdown,
)


def _sample_product_readiness_report(*, passed: bool) -> ProductReadinessReport:
    return ProductReadinessReport(
        schema_version="product_readiness_report_v1",
        generated_at=datetime(2026, 3, 12, 0, 0, tzinfo=UTC).isoformat(),
        report_version="ProductReadinessReport v1",
        components=(
            ProductReadinessComponentResult(
                component_id="product_transport",
                label="Product Transport Audit",
                passed=passed,
                scenario_count=3,
                passed_count=3 if passed else 2,
                failure_ids=() if passed else ("ask_cli",),
                detail="coverage:1.0000" if passed else "coverage:0.6667",
            ),
            ProductReadinessComponentResult(
                component_id="deployment_smoke",
                label="Deployment Smoke",
                passed=True,
                scenario_count=49,
                passed_count=49,
                failure_ids=(),
                detail="pass_rate:1.0000",
            ),
            ProductReadinessComponentResult(
                component_id="frontend_gate",
                label="Phase M Frontend Gate",
                passed=True,
                scenario_count=6,
                passed_count=6,
                failure_ids=(),
                detail="flow:11/11",
            ),
        ),
    )


def test_product_readiness_report_passes_on_current_assets() -> None:
    report = evaluate_product_readiness_report()

    assert report.schema_version == "product_readiness_report_v1"
    assert report.report_version == "ProductReadinessReport v1"
    assert tuple(component.component_id for component in report.components) == (
        "product_transport",
        "deployment_smoke",
        "frontend_gate",
    )
    assert report.component_count == 3
    assert report.passed_component_count == 3
    assert report.failure_ids == ()
    assert report.passed is True


def test_product_readiness_report_round_trips_json(tmp_path: Path) -> None:
    report = evaluate_product_readiness_report()

    output_path = write_product_readiness_report_json(
        tmp_path / "product_readiness_report.json",
        report,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    restored = read_product_readiness_report_json(output_path)

    assert payload["schema_version"] == "product_readiness_report_v1"
    assert payload["report_version"] == "ProductReadinessReport v1"
    assert payload["passed"] is True
    assert payload["passed_component_count"] == 3
    assert restored == report


def test_assert_product_readiness_report_rejects_failed_component() -> None:
    report = _sample_product_readiness_report(passed=False)

    with pytest.raises(RuntimeError, match="product readiness gate failed"):
        assert_product_readiness_report(report)


def test_product_readiness_report_markdown_renders_stable_summary() -> None:
    report = _sample_product_readiness_report(passed=False)

    markdown = render_product_readiness_report_markdown(
        report,
        title="Product Readiness Gate",
    )

    assert markdown.startswith("# Product Readiness Gate\n")
    assert "| Component | Status | Passed | Total | Coverage | Failure IDs | Detail |" in markdown
    assert (
        "| Product Transport Audit | FAIL | 2 | 3 | 0.6667 | ask_cli | coverage:0.6667 |"
        in markdown
    )
    assert "Failing components: `product_transport`" in markdown


def test_product_readiness_report_markdown_is_written_to_disk(tmp_path: Path) -> None:
    report = _sample_product_readiness_report(passed=True)

    output_path = write_product_readiness_report_markdown(
        tmp_path / "product_readiness_report.md",
        report,
        title="Product Readiness Report",
    )

    markdown = output_path.read_text(encoding="utf-8")
    assert output_path.exists()
    assert markdown.startswith("# Product Readiness Report\n")
    assert "- Status: `PASS`" in markdown


def test_product_readiness_report_main_prints_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_path = tmp_path / "product_readiness_report.json"
    markdown_output_path = tmp_path / "product_readiness_report.md"

    exit_code = product_readiness_report_main(
        [
            "--output",
            str(output_path),
            "--markdown-output",
            str(markdown_output_path),
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
    assert markdown_output_path.exists()
    output = capsys.readouterr().out
    assert "Product readiness report" in output
    assert f"markdown_path={markdown_output_path}" in output
    assert "product_transport=PASS:" in output
    assert "deployment_smoke=PASS:" in output
    assert "frontend_gate=PASS:" in output
    assert "product_readiness_report=PASS" in output


def test_product_readiness_gate_main_prints_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_path = tmp_path / "product_readiness_gate.json"
    markdown_output_path = tmp_path / "product_readiness_gate.md"

    exit_code = product_readiness_gate_main(
        [
            "--output",
            str(output_path),
            "--markdown-output",
            str(markdown_output_path),
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
    assert markdown_output_path.exists()
    output = capsys.readouterr().out
    assert "Product readiness gate" in output
    assert f"markdown_path={markdown_output_path}" in output
    assert "passed_component_count=3" in output
    assert "product_readiness_gate=PASS" in output


def test_product_readiness_gate_main_fails_and_persists_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failing_report = _sample_product_readiness_report(passed=False)
    monkeypatch.setattr(
        "mind.cli.evaluate_product_readiness_report", lambda repo_root: failing_report
    )

    output_path = tmp_path / "product_readiness_gate_fail.json"
    markdown_output_path = tmp_path / "product_readiness_gate_fail.md"
    with pytest.raises(SystemExit, match="product readiness gate failed"):
        product_readiness_gate_main(
            [
                "--output",
                str(output_path),
                "--markdown-output",
                str(markdown_output_path),
            ]
        )

    assert output_path.exists()
    assert markdown_output_path.exists()
    assert "Failing components: `product_transport`" in markdown_output_path.read_text(
        encoding="utf-8"
    )
