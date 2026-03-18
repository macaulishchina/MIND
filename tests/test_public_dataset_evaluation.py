"""Tests for unified public-dataset evaluation helpers and report CLI."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from mind.app.context import ProviderSelection
from mind.cli_phase_gates import public_dataset_report_main
from mind.fixtures import evaluate_public_dataset, write_public_dataset_evaluation_report_json
from mind.fixtures.public_datasets.registry import build_public_dataset_objects
from mind.kernel.store import SQLiteMemoryStore
from mind.workspace.builder import WorkspaceBuilder


@pytest.fixture(autouse=True)
def _isolate_from_repo_config() -> None:  # type: ignore[misc]
    """Prevent repo-root mind.toml from leaking into test expectations."""
    with patch("mind.capabilities.config_file.load_mind_toml", return_value={}):
        yield


def test_evaluate_public_dataset_local_source_builds_interpretable_report() -> None:
    """Verify local-source evaluation returns a stable, interpretable report."""

    report = evaluate_public_dataset("locomo", source_path=_source_path("locomo"))

    assert report.dataset_name == "locomo"
    assert report.fixture_name == "locomo local-slice-v1"
    assert report.object_count == 10
    assert report.retrieval_case_count == 3
    assert report.answer_case_count == 2
    assert report.long_horizon_sequence_count == 1
    assert report.answer_provider == "stub"
    assert report.answer_model == "deterministic"
    assert report.answer_provider_configured is True
    assert report.long_horizon_strategy == "public_dataset_optimized_v1"
    assert report.workspace.keyword_case_count == 2
    assert report.workspace.time_window_case_count == 1
    assert report.workspace.vector_case_count == 0
    assert report.workspace.workspace_task_success_rate == 1.0
    assert len(report.fixture_hash) == 64
    assert len(report.findings) == 3


def test_evaluate_public_dataset_supports_vector_cases() -> None:
    """Verify evaluation summaries capture vector retrieval coverage."""

    report = evaluate_public_dataset("scifact", source_path=_source_path("scifact"))

    assert report.workspace.vector_case_count == 1
    assert report.workspace.case_count == 3
    assert report.workspace.workspace_answer_quality_score >= 0.8
    assert report.long_horizon.average_pus >= 0.3


def test_evaluate_public_dataset_hotpotqa_reaches_positive_long_horizon_pus() -> None:
    """Verify HotpotQA local slices clear the positive long-horizon threshold."""

    report = evaluate_public_dataset("hotpotqa", source_path=_source_path("hotpotqa"))

    assert report.long_horizon.average_pus >= 0.4
    assert report.long_horizon.average_task_success_rate >= 0.6


def test_evaluate_public_dataset_hotpotqa_preserves_reuse_signal() -> None:
    """Verify public-dataset long-horizon optimization keeps a non-zero reuse rate."""

    report = evaluate_public_dataset("hotpotqa", source_path=_source_path("hotpotqa"))

    assert report.long_horizon.average_reuse_rate > 0.0


def test_public_dataset_evaluation_report_json_round_trip_shape(tmp_path: Path) -> None:
    """Verify evaluation reports can be persisted as JSON for dev workflows."""

    report = evaluate_public_dataset("hotpotqa", source_path=_source_path("hotpotqa"))
    output_path = write_public_dataset_evaluation_report_json(tmp_path / "report.json", report)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["dataset_name"] == "hotpotqa"
    assert payload["fixture_name"] == "hotpotqa local-slice-v1"
    assert payload["answer_provider"] == "stub"
    assert payload["answer_provider_configured"] is True
    assert payload["long_horizon_strategy"] == "public_dataset_optimized_v1"
    assert payload["workspace"]["case_count"] == 2
    assert payload["workspace"]["workspace_gold_fact_coverage"] == 1.0
    assert payload["workspace"]["workspace_task_success_rate"] == 1.0
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
    assert "answer_provider=stub" in output
    assert "answer_provider_configured=true" in output
    assert "long_horizon_strategy=public_dataset_optimized_v1" in output
    assert "candidate_recall_at_20=" in output
    assert "average_pus=" in output
    assert "public_dataset_report=PASS" in output


def test_workspace_builder_promotes_summary_for_selected_episode(tmp_path: Path) -> None:
    """Verify workspace selection keeps a paired summary with a selected episode."""

    objects = build_public_dataset_objects("hotpotqa", source_path=_source_path("hotpotqa"))
    candidate_ids = [
        "hotpotqa-local-episode-001",
        "hotpotqa-local-episode-001-raw-01",
        "hotpotqa-local-episode-002",
        "hotpotqa-local-episode-002-summary",
        "hotpotqa-local-episode-001-summary",
    ]
    candidate_scores = [0.43, 0.35, 0.28, 0.23, 0.22]

    with SQLiteMemoryStore(tmp_path / "workspace.sqlite3") as store:
        store.insert_objects(objects)
        result = WorkspaceBuilder(store).build(
            task_id="hotpotqa-local-task-001",
            candidate_ids=candidate_ids,
            candidate_scores=candidate_scores,
            slot_limit=4,
        )

    assert "hotpotqa-local-episode-001" in result.selected_ids
    assert "hotpotqa-local-episode-001-summary" in result.selected_ids


def test_evaluate_public_dataset_accepts_provider_selection_and_strategy() -> None:
    """Verify report generation accepts explicit provider and strategy settings."""

    report = evaluate_public_dataset(
        "hotpotqa",
        source_path=_source_path("hotpotqa"),
        provider_selection=ProviderSelection(provider="openai", model="gpt-4.1-mini"),
        long_horizon_strategy="optimized",
    )

    assert report.answer_provider == "openai"
    assert report.answer_model == "gpt-4.1-mini"
    assert report.answer_provider_configured is False
    assert report.long_horizon_strategy == "optimized_v1"
    assert any("fall back to deterministic" in finding for finding in report.findings)


def _source_path(dataset_name: str) -> Path:
    return Path(__file__).resolve().parent / "data" / "public_datasets" / (
        f"{dataset_name}_local_slice.json"
    )