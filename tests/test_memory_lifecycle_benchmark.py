"""Tests for the end-to-end memory lifecycle benchmark."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from mind.eval import (
    evaluate_memory_lifecycle_benchmark,
    write_memory_lifecycle_benchmark_report_json,
)


@pytest.fixture(autouse=True)
def _isolate_from_repo_config() -> None:  # type: ignore[misc]
    """Prevent repo-root mind.toml from affecting benchmark test expectations."""

    with patch("mind.capabilities.config_file.load_mind_toml", return_value={}):
        yield


def test_evaluate_memory_lifecycle_benchmark_tracks_stage_growth(tmp_path: Path) -> None:
    """Verify lifecycle benchmark stages create the expected object progression."""

    report = evaluate_memory_lifecycle_benchmark(
        "locomo",
        source_path=_source_path("locomo"),
        telemetry_path=tmp_path / "lifecycle.telemetry.jsonl",
        store_path=tmp_path / "lifecycle.sqlite3",
    )

    assert report.dataset_name == "locomo"
    assert report.bundle_count == 2
    assert report.answer_case_count == 2
    assert report.frontend_debug_query["run_id"] == report.run_id
    assert report.telemetry_path is not None
    assert Path(report.telemetry_path).exists()
    assert report.store_path is not None
    assert Path(report.store_path).exists()

    stages = {stage.stage_name: stage for stage in report.stage_reports}
    assert tuple(stages) == (
        "remember_only",
        "summarized",
        "reflected",
        "reorganized",
        "schema_promoted",
    )
    assert stages["remember_only"].memory.active_object_counts == {
        "RawRecord": 4,
        "TaskEpisode": 2,
    }
    assert stages["summarized"].memory.active_object_counts["SummaryNote"] == 2
    assert stages["reflected"].memory.active_object_counts["ReflectionNote"] == 2
    assert stages["schema_promoted"].memory.active_object_counts["SchemaNote"] == 1
    assert stages["schema_promoted"].cost.offline_job_count == 1
    assert stages["schema_promoted"].ask.answer_case_count == 2
    assert 0.0 <= stages["schema_promoted"].ask.average_answer_quality <= 1.0


def test_memory_lifecycle_benchmark_report_json_round_trip(tmp_path: Path) -> None:
    """Verify lifecycle benchmark reports persist with telemetry metadata."""

    report = evaluate_memory_lifecycle_benchmark(
        "locomo",
        source_path=_source_path("locomo"),
        telemetry_path=tmp_path / "roundtrip.telemetry.jsonl",
        store_path=tmp_path / "roundtrip.sqlite3",
    )
    output_path = write_memory_lifecycle_benchmark_report_json(tmp_path / "report.json", report)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["dataset_name"] == "locomo"
    assert payload["answer_case_count"] == 2
    assert payload["frontend_debug_query"]["run_id"] == report.run_id
    assert payload["stage_reports"][-1]["stage_name"] == "schema_promoted"
    assert payload["stage_reports"][-1]["cost"]["offline_job_count"] == 1
    assert payload["telemetry_path"].endswith("roundtrip.telemetry.jsonl")


def _source_path(dataset_name: str) -> Path:
    return Path(__file__).resolve().parent / "data" / "public_datasets" / (
        f"{dataset_name}_local_slice.json"
    )