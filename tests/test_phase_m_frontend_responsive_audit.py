from __future__ import annotations

import json
from pathlib import Path
import shutil

from mind.fixtures import build_frontend_experience_bench_v1
from mind.frontend import (
    evaluate_frontend_responsive_audit,
    write_frontend_responsive_audit_json,
)


def test_frontend_responsive_audit_passes_on_current_static_frontend() -> None:
    result = evaluate_frontend_responsive_audit()

    expected_count = sum(
        scenario.viewport in {"desktop", "mobile"}
        for scenario in build_frontend_experience_bench_v1()
    )
    assert result.scenario_count == expected_count
    assert result.desktop_total > 0
    assert result.mobile_total > 0
    assert result.viewport_meta_present is True
    assert result.fluid_shell_present is True
    assert result.responsive_grid_present is True
    assert result.failure_ids == ()
    assert result.coverage == 1.0
    assert result.passed is True


def test_frontend_responsive_audit_report_writes_json(tmp_path: Path) -> None:
    result = evaluate_frontend_responsive_audit()

    output_path = write_frontend_responsive_audit_json(
        tmp_path / "phase_m_responsive_audit.json",
        result,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "frontend_responsive_audit_v1"
    assert payload["passed"] is True
    assert payload["coverage"] == 1.0


def test_frontend_responsive_audit_fails_when_mobile_markers_are_missing(
    tmp_path: Path,
) -> None:
    frontend_root = Path(__file__).resolve().parents[1] / "frontend"
    html = (frontend_root / "index.html").read_text(encoding="utf-8")
    js = (frontend_root / "app.js").read_text(encoding="utf-8")
    css = (frontend_root / "styles" / "workspaces.css").read_text(encoding="utf-8")

    broken_root = tmp_path / "frontend"
    broken_root.mkdir()
    (broken_root / "index.html").write_text(
        html.replace('content="width=device-width, initial-scale=1"', 'content="initial-scale=1"'),
        encoding="utf-8",
    )
    (broken_root / "app.js").write_text(js, encoding="utf-8")
    shutil.copytree(frontend_root / "app", broken_root / "app")
    shutil.copytree(frontend_root / "styles", broken_root / "styles")
    (broken_root / "styles" / "workspaces.css").write_text(
        css.replace("repeat(auto-fit, minmax(20rem, 1fr))", "repeat(1, minmax(20rem, 1fr))"),
        encoding="utf-8",
    )

    result = evaluate_frontend_responsive_audit(broken_root)

    assert result.passed is False
    assert result.viewport_meta_present is False
    assert result.responsive_grid_present is False
    assert result.mobile_pass_count < result.mobile_total
    assert result.failure_ids
