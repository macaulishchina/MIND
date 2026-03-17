"""Tests for unified public-dataset evaluation helpers and report CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mind.cli_phase_gates import public_dataset_report_main
from mind.fixtures import evaluate_public_dataset, write_public_dataset_evaluation_report_json


def test_evaluate_public_dataset_local_source_builds_interpretable_report() -> None:
    """Verify local-source evaluation returns a stable, interpretable report."""

    report = evaluate_public_dataset("locomo", source_path=_source_path("locomo"))

    assert report.dataset_name == "locomo"
    assert report.fixture_name == "locomo local-slice-v1"
    assert report.object_count == 10
    assert report.retrieval_case_count == 3
    assert report.answer_case_count == 2
    assert report.long_horizon_sequence_count == 1
    assert report.workspace.keyword_case_count == 2
    assert report.workspace.time_window_case_count == 1
    assert report.workspace.vector_case_count == 0
    assert len(report.fixture_hash) == 64
    assert len(report.findings) == 3


def test_evaluate_public_dataset_supports_vector_cases() -> None:
    """Verify evaluation summaries capture vector retrieval coverage."""

    report = evaluate_public_dataset("scifact", source_path=_source_path("scifact"))

    assert report.workspace.vector_case_count == 1
    assert report.workspace.case_count == 3
    assert 0.0 <= report.long_horizon.average_pus <= 1.0


def test_public_dataset_evaluation_report_json_round_trip_shape(tmp_path: Path) -> None:
    """Verify evaluation reports can be persisted as JSON for dev workflows."""

    report = evaluate_public_dataset("hotpotqa", source_path=_source_path("hotpotqa"))
    output_path = write_public_dataset_evaluation_report_json(tmp_path / "report.json", report)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["dataset_name"] == "hotpotqa"
    assert payload["fixture_name"] == "hotpotqa local-slice-v1"
    assert payload["workspace"]["case_count"] == 2
    assert payload["long_horizon"]["sequence_count"] == 1
    assert len(payload["findings"]) == 3


def test_public_dataset_report_main_persists_report_and_prints_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify the formal CLI report entrypoint persists and summarizes evaluation."""

    output_path = tmp_path / "locomo_report.json"

    exit_code = public_dataset_report_main(
        [
            "locomo",
            "--source",
            str(_source_path("locomo")),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["dataset_name"] == "locomo"
    output = capsys.readouterr().out
    assert "Public dataset report" in output
    assert f"report_path={output_path}" in output
    assert "candidate_recall_at_20=" in output
    assert "average_pus=" in output
    assert "public_dataset_report=PASS" in output


def _source_path(dataset_name: str) -> Path:
    return Path(__file__).resolve().parent / "data" / "public_datasets" / (
        f"{dataset_name}_local_slice.json"
    )