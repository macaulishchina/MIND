from __future__ import annotations

import json
from pathlib import Path

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
    assert result.frontend_gate_pass is True
    assert_frontend_gate(result)


def test_frontend_gate_report_writes_json(tmp_path: Path) -> None:
    result = evaluate_frontend_gate()

    output_path = write_frontend_gate_report_json(tmp_path / "phase_m_gate.json", result)
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    restored = read_frontend_gate_report_json(output_path)

    assert payload["schema_version"] == "frontend_gate_report_v1"
    assert payload["frontend_gate_pass"] is True
    assert payload["m6_pass"] is True
    assert restored["schema_version"] == "frontend_gate_report_v1"
    assert restored["frontend_gate_pass"] is True


def test_frontend_gate_fails_when_transport_surface_regresses(tmp_path: Path) -> None:
    frontend_root = Path(__file__).resolve().parents[1] / "frontend"
    broken_root = tmp_path / "frontend"
    broken_root.mkdir()

    for name in ("index.html", "app.js", "styles.css"):
        (broken_root / name).write_text(
            (frontend_root / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    (broken_root / "api.js").write_text(
        (frontend_root / "api.js")
        .read_text(encoding="utf-8")
        .replace('"/v1/frontend/settings:restore"', '"/v1/frontend/settings:noop"'),
        encoding="utf-8",
    )

    result = evaluate_frontend_gate(frontend_root=broken_root)

    assert result.frontend_gate_pass is False
    assert result.m4_pass is False
    assert result.m5_pass is True
