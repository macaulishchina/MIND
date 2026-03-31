from __future__ import annotations

import json
from pathlib import Path

from mind.config.manager import _DEFAULT_TEST_TOML
from tests.eval.runners.eval_owner_centered_add import DatasetSpec
from tests.eval.runners.eval_owner_centered_add import build_report
from tests.eval.runners.eval_owner_centered_add import build_summary
from tests.eval.runners.eval_owner_centered_add import _case_owner_lookup
from tests.eval.runners.eval_owner_centered_add import _evaluate_case
from tests.eval.runners.eval_owner_centered_add import _evaluate_dataset_cases
from tests.eval.runners.eval_owner_centered_add import _load_dataset


DATASET_PATH = Path("tests/eval/datasets/owner_centered_add_cases.json")
FEATURE_DATASET_PATH = Path("tests/eval/datasets/owner_centered_feature_cases.json")
RELATION_DATASET_PATH = Path("tests/eval/datasets/owner_centered_relationship_cases.json")


def test_owner_centered_dataset_loads() -> None:
    dataset = _load_dataset(DATASET_PATH)

    assert dataset.name == "owner_centered_add_cases"
    assert len(dataset.cases) == 5


def test_owner_centered_feature_dataset_loads() -> None:
    dataset = _load_dataset(FEATURE_DATASET_PATH)

    assert dataset.name == "owner_centered_feature_cases"
    assert len(dataset.cases) == 4


def test_owner_centered_relationship_dataset_loads() -> None:
    dataset = _load_dataset(RELATION_DATASET_PATH)

    assert dataset.name == "owner_centered_relationship_cases"
    assert len(dataset.cases) == 8


def test_case_owner_lookup_supports_known_and_anonymous_owners() -> None:
    assert _case_owner_lookup(
        {"owner": {"external_user_id": "alice"}}
    ) == "alice"
    assert _case_owner_lookup(
        {"owner": {"anonymous_session_id": "anon-1"}}
    ) == "anon-1"


def test_owner_centered_eval_case_passes_for_update_scenario(memory_config) -> None:
    dataset = _load_dataset(DATASET_PATH)
    update_case = next(case for case in dataset.cases if case["id"] == "owner-add-005")

    result = _evaluate_case(memory_config, update_case)

    assert result.case_pass is True
    assert result.count_pass is True
    assert result.owner_pass is True
    assert result.update_hits == result.update_total == 2
    assert result.failures == []


def test_owner_centered_report_and_summary_render(tmp_path, memory_config) -> None:
    dataset = _load_dataset(DATASET_PATH)
    case_results = _evaluate_dataset_cases(memory_config, dataset, concurrency=2)

    report = build_report(dataset, case_results, _DEFAULT_TEST_TOML)
    output_path = tmp_path / "owner_centered_report.json"
    output_path.write_text(json.dumps(report), encoding="utf-8")
    summary = build_summary(report, output_path)

    assert report["metrics"]["case_pass_rate"] == 1.0
    assert report["metrics"]["canonical_text_accuracy"] == 1.0
    assert "Owner-Centered Add Evaluation Summary" in summary


def test_owner_centered_feature_dataset_cases_pass(memory_config) -> None:
    dataset = _load_dataset(FEATURE_DATASET_PATH)

    case_results = _evaluate_dataset_cases(memory_config, dataset, concurrency=2)

    assert all(result.case_pass for result in case_results)


def test_owner_centered_relationship_representative_cases_pass(memory_config) -> None:
    dataset = _load_dataset(RELATION_DATASET_PATH)
    selected_ids = {
        "owner-rel-inverse-001",
        "owner-rel-stable-001",
        "owner-rel-split-001",
        "owner-rel-owner-002",
    }
    selected_dataset = DatasetSpec(
        path=dataset.path,
        name=dataset.name,
        focus=dataset.focus,
        description=dataset.description,
        cases=[case for case in dataset.cases if case["id"] in selected_ids],
    )

    case_results = _evaluate_dataset_cases(memory_config, selected_dataset, concurrency=2)

    assert len(case_results) == len(selected_ids)
    assert all(result.case_pass for result in case_results)


def test_owner_centered_dataset_concurrency_preserves_case_order(memory_config) -> None:
    dataset = _load_dataset(DATASET_PATH)

    case_results = _evaluate_dataset_cases(memory_config, dataset, concurrency=3)

    assert [result.case_id for result in case_results] == [
        case["id"] for case in dataset.cases
    ]
    assert all(result.case_pass for result in case_results)


def test_report_includes_dataset_metadata() -> None:
    report = build_report(
        DatasetSpec(
            path=DATASET_PATH,
            name="owner_centered_add_cases",
            focus="owner-centered add integration",
            description="",
            cases=[],
        ),
        [],
        _DEFAULT_TEST_TOML,
    )

    assert report["dataset_name"] == "owner_centered_add_cases"
    assert "statement_accuracy" in report["metrics"]
