from __future__ import annotations

import json
from pathlib import Path

from mind.governance import (
    assert_governance_gate,
    evaluate_governance_gate,
    write_governance_gate_report_json,
)


def test_phase_h_gate_passes_current_thresholds(tmp_path: Path) -> None:
    result = evaluate_governance_gate(tmp_path / "phase_h_gate.sqlite3")

    assert_governance_gate(result)
    assert result.h1_pass
    assert result.h2_pass
    assert result.h3_pass
    assert result.h4_pass
    assert result.h5_pass
    assert result.h6_pass
    assert result.h7_pass
    assert result.h8_pass
    assert result.governance_gate_pass
    assert result.governance_audit_stage_sequence == ("plan", "preview", "execute")


def test_phase_h_gate_report_writes_json(tmp_path: Path) -> None:
    result = evaluate_governance_gate(tmp_path / "phase_h_report.sqlite3")

    output_path = write_governance_gate_report_json(tmp_path / "phase_h_report.json", result)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "governance_gate_report_v1"
    assert payload["governance_gate_pass"] is True
    assert payload["governance_audit_stage_sequence"] == ["plan", "preview", "execute"]
