from __future__ import annotations

import json
from pathlib import Path

from mind.config import ConfigManager
from mind.config.manager import _DEFAULT_TEST_TOML
from tests.eval.runners.eval_owner_centered_add import _case_owner_lookup
from tests.eval.runners.eval_owner_centered_add import _evaluate_case
from tests.eval.runners.eval_owner_centered_add import _load_dataset
from tests.eval.runners.eval_owner_centered_add import build_report
from tests.eval.runners.eval_owner_centered_add import build_summary


DATASET_PATH = Path("tests/eval/datasets/owner_centered_add_cases.json")
FEATURE_DATASET_PATH = Path("tests/eval/datasets/owner_centered_feature_cases.json")
RELATION_DATASET_PATH = Path("tests/eval/datasets/owner_centered_relationship_cases.json")


def test_owner_centered_dataset_loads() -> None:
    dataset = _load_dataset(DATASET_PATH)

    assert dataset.name == "owner_centered_add_cases"
    assert len(dataset.cases) >= 5


def test_owner_centered_feature_dataset_loads() -> None:
    dataset = _load_dataset(FEATURE_DATASET_PATH)

    assert dataset.name == "owner_centered_feature_cases"
    assert len(dataset.cases) >= 4


def test_owner_centered_relationship_dataset_loads() -> None:
    dataset = _load_dataset(RELATION_DATASET_PATH)

    assert dataset.name == "owner_centered_relationship_cases"
    assert len(dataset.cases) >= 50


def test_case_owner_lookup_supports_known_and_anonymous_owners() -> None:
    assert _case_owner_lookup(
        {"owner": {"external_user_id": "alice"}}
    ) == "alice"
    assert _case_owner_lookup(
        {"owner": {"anonymous_session_id": "anon-1"}}
    ) == "anon-1"


def test_owner_centered_eval_case_passes_for_update_scenario() -> None:
    cfg = ConfigManager(toml_path=_DEFAULT_TEST_TOML).get()
    dataset = _load_dataset(DATASET_PATH)
    update_case = next(case for case in dataset.cases if case["id"] == "owner-add-005")

    result = _evaluate_case(cfg, update_case)

    assert result.case_pass is True
    assert result.count_pass is True
    assert result.owner_pass is True
    assert result.update_hits == result.update_total == 2
    assert result.failures == []


def test_owner_centered_report_and_summary_render(tmp_path) -> None:
    cfg = ConfigManager(toml_path=_DEFAULT_TEST_TOML).get()
    dataset = _load_dataset(DATASET_PATH)
    case_results = [_evaluate_case(cfg, case) for case in dataset.cases]

    report = build_report(dataset, case_results, _DEFAULT_TEST_TOML)
    output_path = tmp_path / "owner_centered_report.json"
    output_path.write_text(json.dumps(report), encoding="utf-8")
    summary = build_summary(report, output_path)

    assert report["metrics"]["case_pass_rate"] == 1.0
    assert report["metrics"]["canonical_text_accuracy"] == 1.0
    assert "Owner-Centered Add Evaluation Summary" in summary


def test_owner_centered_feature_dataset_cases_pass() -> None:
    cfg = ConfigManager(toml_path=_DEFAULT_TEST_TOML).get()
    dataset = _load_dataset(FEATURE_DATASET_PATH)

    case_results = [_evaluate_case(cfg, case) for case in dataset.cases]

    assert all(result.case_pass for result in case_results)


def test_owner_centered_relationship_representative_cases_pass() -> None:
    cfg = ConfigManager(toml_path=_DEFAULT_TEST_TOML).get()
    dataset = _load_dataset(RELATION_DATASET_PATH)
    selected_ids = {
        "owner-rel-inverse-001",
        "owner-rel-stable-001",
        "owner-rel-split-001",
        "owner-rel-owner-002",
    }

    case_results = [
        _evaluate_case(cfg, case)
        for case in dataset.cases
        if case["id"] in selected_ids
    ]

    assert len(case_results) == len(selected_ids)
    assert all(result.case_pass for result in case_results)
