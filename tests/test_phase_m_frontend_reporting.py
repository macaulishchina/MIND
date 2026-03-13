from __future__ import annotations

import json
from pathlib import Path
import shutil

from mind.fixtures import build_frontend_experience_bench_v1
from mind.frontend import (
    evaluate_frontend_flow_report,
    read_frontend_flow_report_json,
    write_frontend_flow_report_json,
)


def test_frontend_flow_report_passes_on_current_static_frontend() -> None:
    report = evaluate_frontend_flow_report()

    assert report.bench_version == "FrontendExperienceBench v1"
    assert report.scenario_count == len(build_frontend_experience_bench_v1())
    assert report.required_experience_entrypoints == (
        "ingest",
        "retrieve",
        "access",
        "offline",
        "gate_demo",
    )
    assert report.covered_experience_entrypoints == report.required_experience_entrypoints
    assert report.transport_surface_present is True
    assert report.responsive_audit_pass is True
    assert report.experience_flow_pass is True
    assert report.contract_audit_pass is True
    assert report.config_audit_pass is True
    assert report.debug_ui_audit_pass is True
    assert report.dev_mode_guard_pass is True
    assert report.failure_ids == ()
    assert report.coverage == 1.0
    assert report.passed is True


def test_frontend_flow_report_round_trips_json(tmp_path: Path) -> None:
    report = evaluate_frontend_flow_report()

    output_path = write_frontend_flow_report_json(
        tmp_path / "phase_m_flow_report.json",
        report,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    restored = read_frontend_flow_report_json(output_path)

    assert payload["schema_version"] == "frontend_flow_report_v1"
    assert payload["passed"] is True
    assert payload["coverage"] == 1.0
    assert payload["contract_audit_pass"] is True
    assert restored == report


def test_frontend_flow_report_fails_when_transport_surface_regresses(
    tmp_path: Path,
) -> None:
    frontend_root = Path(__file__).resolve().parents[1] / "frontend"
    broken_root = tmp_path / "frontend"
    broken_root.mkdir()

    (broken_root / "index.html").write_text(
        (frontend_root / "index.html").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    shutil.copytree(frontend_root / "app", broken_root / "app")
    shutil.copytree(frontend_root / "styles", broken_root / "styles")
    (broken_root / "app.js").write_text(
        (frontend_root / "app.js").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (broken_root / "api.js").write_text(
        (frontend_root / "api.js")
        .read_text(encoding="utf-8")
        .replace('"/v1/frontend/settings:apply"', '"/v1/frontend/settings:noop"'),
        encoding="utf-8",
    )

    report = evaluate_frontend_flow_report(broken_root)

    assert report.passed is False
    assert report.transport_surface_present is False
    assert report.config_audit_pass is False
    assert "config_dev_mode_toggle_desktop" in report.failure_ids
    scenario = next(
        item for item in report.scenario_results if item.scenario_id == "config_dev_mode_toggle_desktop"
    )
    assert 'transport:"/v1/frontend/settings:apply"' in scenario.missing_checks


def test_frontend_flow_report_fails_when_access_answer_contract_regresses(
    tmp_path: Path,
) -> None:
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

    report = evaluate_frontend_flow_report(broken_root)

    assert report.passed is False
    assert report.contract_audit_pass is False
    assert report.transport_surface_present is True
    assert "access_run_auto_desktop" in report.failure_ids
    scenario = next(
        item for item in report.scenario_results if item.scenario_id == "access_run_auto_desktop"
    )
    assert "contract:js:result.answer" in scenario.missing_checks
