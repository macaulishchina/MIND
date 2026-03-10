from __future__ import annotations

import json
from pathlib import Path

from mind.access import (
    AccessMode,
    assert_phase_i_gate,
    evaluate_phase_i_gate,
    write_phase_i_gate_report_json,
)


def test_phase_i_gate_passes_current_thresholds(tmp_path: Path) -> None:
    result = evaluate_phase_i_gate(tmp_path / "phase_i_gate.sqlite3")

    assert_phase_i_gate(result)
    assert result.i1_pass
    assert result.i2_pass
    assert result.i3_pass
    assert result.i4_pass
    assert result.i5_pass
    assert result.i6_pass
    assert result.i7_pass
    assert result.i8_pass
    assert result.phase_i_pass
    assert set(result.callable_modes) == {
        AccessMode.AUTO,
        AccessMode.FLASH,
        AccessMode.RECALL,
        AccessMode.RECONSTRUCT,
        AccessMode.REFLECTIVE_ACCESS,
    }
    assert result.auto_audit.upgrade_count > 0
    assert result.auto_audit.downgrade_count > 0
    assert result.auto_audit.jump_count > 0


def test_phase_i_gate_report_writes_json(tmp_path: Path) -> None:
    result = evaluate_phase_i_gate(tmp_path / "phase_i_report.sqlite3")

    output_path = write_phase_i_gate_report_json(tmp_path / "phase_i_report.json", result)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "phase_i_gate_report_v1"
    assert payload["phase_i_pass"] is True
    assert sorted(payload["callable_modes"]) == [
        "auto",
        "flash",
        "recall",
        "reconstruct",
        "reflective_access",
    ]
    assert payload["auto_audit"]["upgrade_count"] > 0
    assert payload["auto_audit"]["downgrade_count"] > 0
    assert payload["auto_audit"]["jump_count"] > 0
