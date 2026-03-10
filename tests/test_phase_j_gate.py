from __future__ import annotations

import json
from pathlib import Path

import pytest

from mind.cli_gate import (
    CliGateResult,
    _AuditOutcome,
    assert_cli_gate,
    evaluate_cli_gate,
    write_cli_gate_report_json,
)


def test_phase_j_gate_passes_current_thresholds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "mind.cli_gate._evaluate_help_audit",
        lambda: _AuditOutcome(pass_count=9, total=9),
    )
    monkeypatch.setattr(
        "mind.cli_gate._evaluate_family_reachability_audit",
        lambda: _AuditOutcome(pass_count=8, total=8),
    )
    monkeypatch.setattr(
        "mind.cli_gate._evaluate_representative_flow_audit",
        lambda dsn: _AuditOutcome(pass_count=5, total=5),
    )
    monkeypatch.setattr(
        "mind.cli_gate._evaluate_config_audit",
        lambda: _AuditOutcome(pass_count=20, total=20),
    )
    monkeypatch.setattr(
        "mind.cli_gate._evaluate_output_contract_audit",
        lambda: _AuditOutcome(pass_count=8, total=8),
    )
    monkeypatch.setattr(
        "mind.cli_gate._evaluate_invalid_exit_audit",
        lambda: _AuditOutcome(pass_count=5, total=5),
    )
    monkeypatch.setattr(
        "mind.cli_gate._evaluate_wrapped_regression_audit",
        lambda: _AuditOutcome(pass_count=5, total=5),
    )

    result = evaluate_cli_gate(postgres_admin_dsn="postgresql+psycopg://admin")

    assert_cli_gate(result)
    assert result.j1_pass
    assert result.j2_pass
    assert result.j3_pass
    assert result.j4_pass
    assert result.j5_pass
    assert result.j6_pass
    assert result.cli_gate_pass
    assert result.postgres_demo_configured is True
    assert result.scenario_count == 26
    assert result.scenario_family_count == 9


def test_phase_j_gate_report_writes_json(tmp_path: Path) -> None:
    result = CliGateResult(
        scenario_count=26,
        scenario_family_count=9,
        help_coverage_count=9,
        help_total=9,
        family_reachability_count=8,
        family_total=8,
        representative_flow_pass_count=5,
        representative_flow_total=5,
        config_audit_pass_count=20,
        config_audit_total=20,
        output_contract_pass_count=8,
        output_contract_total=8,
        invalid_exit_coverage_count=5,
        invalid_exit_total=5,
        wrapped_regression_pass_count=5,
        wrapped_regression_total=5,
        postgres_demo_configured=True,
        help_failures=(),
        family_failures=(),
        representative_flow_failures=(),
        config_audit_failures=(),
        output_contract_failures=(),
        invalid_exit_failures=(),
        wrapped_regression_failures=(),
    )

    output_path = write_cli_gate_report_json(tmp_path / "phase_j_report.json", result)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "cli_gate_report_v1"
    assert payload["cli_gate_pass"] is True
    assert payload["j1_pass"] is True
    assert payload["j6_pass"] is True
    assert payload["scenario_count"] == 26
    assert payload["postgres_demo_configured"] is True
