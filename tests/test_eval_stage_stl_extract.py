from __future__ import annotations

import json
from pathlib import Path

from mind.config.manager import _DEFAULT_TEST_TOML
from tests.eval.runners.eval_cases import DatasetSpec
from tests.eval.runners.eval_cases import _build_stl_extract_report
from tests.eval.runners.eval_cases import _build_stl_messages
from tests.eval.runners.eval_cases import _build_summary
from tests.eval.runners.eval_cases import _cases_for_stage
from tests.eval.runners.eval_cases import _evaluate_cases
from tests.eval.runners.eval_cases import _evaluate_stl_extract_case
from tests.eval.runners.eval_cases import _load_dataset


CASES_DIR = Path("tests/eval/cases")


def test_stl_extract_stage_evaluates_feature_case(memory_config) -> None:
    dataset = _cases_for_stage(_load_dataset(CASES_DIR), "stl_extract")
    case = next(case for case in dataset.cases if case["id"] == "owner-feature-001")

    result = _evaluate_stl_extract_case(memory_config, case)

    assert result.case_pass is True
    assert result.ref_hits == result.ref_total
    assert result.statement_hits == result.statement_total


def test_stl_extract_messages_flatten_shared_turns() -> None:
    case = {
        "turns": [
            {"messages": [{"role": "user", "content": "I hope Tom comes"}]},
            {"messages": [{"role": "assistant", "content": "Why Tom?"}]},
        ]
    }

    messages = _build_stl_messages(case)

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "User: I hope Tom comes" in messages[1]["content"]
    assert "Assistant: Why Tom?" in messages[1]["content"]


def test_stl_extract_report_and_summary_render(tmp_path: Path, memory_config) -> None:
    dataset = _cases_for_stage(_load_dataset(CASES_DIR), "stl_extract")
    feature_dataset = DatasetSpec(
        path=dataset.path,
        name=dataset.name,
        cases=[case for case in dataset.cases if case["suite"] == "feature"],
    )
    case_results = _evaluate_cases(
        feature_dataset,
        lambda case: _evaluate_stl_extract_case(memory_config, case),
        concurrency=2,
    )

    report = _build_stl_extract_report(feature_dataset, case_results, _DEFAULT_TEST_TOML)
    output_path = tmp_path / "stl_extract_report.json"
    output_path.write_text(json.dumps(report), encoding="utf-8")
    summary = _build_summary(report, output_path)

    assert report["stage"] == "stl_extract"
    assert report["metrics"]["case_pass_rate"] == 1.0
    assert "STL-Extract Evaluation Summary" in summary


def test_stl_extract_feature_dataset_cases_pass(memory_config) -> None:
    dataset = _cases_for_stage(_load_dataset(CASES_DIR), "stl_extract")
    feature_dataset = DatasetSpec(
        path=dataset.path,
        name=dataset.name,
        cases=[case for case in dataset.cases if case["suite"] == "feature"],
    )

    case_results = _evaluate_cases(
        feature_dataset,
        lambda case: _evaluate_stl_extract_case(memory_config, case),
        concurrency=2,
    )

    assert len(case_results) == 4
    assert all(result.case_pass for result in case_results)


def test_load_single_case_file_for_stl_extract_stage(memory_config) -> None:
    case_path = CASES_DIR / "owner-feature-001.json"
    dataset = _cases_for_stage(_load_dataset(case_path), "stl_extract")
    case_results = _evaluate_cases(
        dataset,
        lambda case: _evaluate_stl_extract_case(memory_config, case),
        concurrency=1,
    )

    assert len(dataset.cases) == 1
    assert dataset.cases[0]["id"] == "owner-feature-001"
    assert len(case_results) == 1
    assert case_results[0].case_pass is True
