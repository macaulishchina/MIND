from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mind.fixtures import ProductTransportAuditReport
from mind.frontend import (
    assert_frontend_gate,
    evaluate_frontend_gate,
    read_frontend_gate_report_json,
    write_frontend_gate_report_json,
)


def test_frontend_gate_passes_on_current_assets() -> None:
    result = evaluate_frontend_gate()

    assert result.m1_pass is True
    assert result.m2_pass is True
    assert result.m3_pass is True
    assert result.m4_pass is True
    assert result.m5_pass is True
    assert result.m6_pass is True
    assert result.product_transport_audit.passed is True
    assert result.frontend_gate_pass is True
    assert_frontend_gate(result)


def test_frontend_gate_report_writes_json(tmp_path: Path) -> None:
    result = evaluate_frontend_gate()

    output_path = write_frontend_gate_report_json(tmp_path / "phase_m_gate.json", result)
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    restored = read_frontend_gate_report_json(output_path)

    assert payload["schema_version"] == "frontend_gate_report_v1"
    assert payload["frontend_gate_pass"] is True
    assert payload["flow_report"]["contract_audit_pass"] is True
    assert payload["product_transport_audit"]["passed"] is True
    assert payload["m6_pass"] is True
    assert restored["schema_version"] == "frontend_gate_report_v1"
    assert restored["frontend_gate_pass"] is True


def test_frontend_gate_fails_when_transport_surface_regresses(tmp_path: Path) -> None:
    frontend_root = Path(__file__).resolve().parents[1] / "frontend"
    broken_root = tmp_path / "frontend"
    broken_root.mkdir()

    for name in ("index.html", "app.js"):
        (broken_root / name).write_text(
            (frontend_root / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    shutil.copytree(frontend_root / "app", broken_root / "app")
    shutil.copytree(frontend_root / "styles", broken_root / "styles")
    (broken_root / "api.js").write_text(
        (frontend_root / "api.js")
        .read_text(encoding="utf-8")
        .replace('"/v1/frontend/settings:apply"', '"/v1/frontend/settings:noop"'),
        encoding="utf-8",
    )

    result = evaluate_frontend_gate(frontend_root=broken_root)

    assert result.frontend_gate_pass is False
    assert result.m4_pass is False
    assert result.product_transport_audit.passed is True
    assert result.m5_pass is True


def test_frontend_gate_fails_when_access_answer_contract_regresses(tmp_path: Path) -> None:
    frontend_root = Path(__file__).resolve().parents[1] / "frontend"
    broken_root = tmp_path / "frontend"
    broken_root.mkdir()

    for name in ("index.html", "api.js"):
        (broken_root / name).write_text(
            (frontend_root / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    shutil.copytree(frontend_root / "app", broken_root / "app")
    shutil.copytree(frontend_root / "styles", broken_root / "styles")
    (broken_root / "app.js").write_text(
        (frontend_root / "app.js")
        .read_text(encoding="utf-8")
        .replace("const answer = result.answer || null;", "const answer = null;"),
        encoding="utf-8",
    )
    (broken_root / "app" / "operation-chain.js").write_text(
        (frontend_root / "app" / "operation-chain.js")
        .read_text(encoding="utf-8")
        .replace("const answer = result.answer || null;", "const answer = null;"),
        encoding="utf-8",
    )

    result = evaluate_frontend_gate(frontend_root=broken_root)

    assert result.frontend_gate_pass is False
    assert result.m1_pass is False
    assert result.m4_pass is True
    assert result.flow_report.contract_audit_pass is False


def test_frontend_gate_fails_when_runtime_transport_audit_regresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "mind.frontend.gate.evaluate_runtime_product_transport_audit_report",
        lambda: ProductTransportAuditReport(
            schema_version="product_transport_audit_v1",
            generated_at=datetime(2026, 3, 12, 0, 0, tzinfo=UTC).isoformat(),
            bench_version="ProductTransportConsistencyScenarios v1",
            scenario_count=3,
            passed_count=2,
            rest_mcp_pair_count=3,
            rest_mcp_match_count=3,
            rest_cli_pair_count=3,
            rest_cli_match_count=2,
            failure_ids=("ask_cli",),
            scenario_results=(),
        ),
    )

    result = evaluate_frontend_gate()

    assert result.flow_report.transport_surface_present is True
    assert result.product_transport_audit.passed is False
    assert result.m4_pass is False
    assert result.frontend_gate_pass is False
