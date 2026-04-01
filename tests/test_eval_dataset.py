from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.eval.runners.eval_cases import _case_messages
from tests.eval.runners.eval_cases import _cases_for_stage
from tests.eval.runners.eval_cases import _load_case_file
from tests.eval.runners.eval_cases import _load_dataset


CASES_DIR = Path("tests/eval/cases")


def test_shared_eval_dataset_loads_all_cases() -> None:
    dataset = _load_dataset(CASES_DIR)

    assert dataset.name == "cases"
    assert len(dataset.cases) == 18


def test_cases_expose_suite_and_stage_blocks() -> None:
    dataset = _load_dataset(CASES_DIR)

    for case in dataset.cases:
        assert case["suite"]
        assert isinstance(case["stages"], dict)
        assert case["stages"]


def test_stage_filtering_uses_shared_case_schema() -> None:
    dataset = _load_dataset(CASES_DIR)

    owner_add_dataset = _cases_for_stage(dataset, "owner_add")
    stl_extract_dataset = _cases_for_stage(dataset, "stl_extract")

    assert len(owner_add_dataset.cases) == 14
    assert len(stl_extract_dataset.cases) == 9
    assert all("owner_add" in case["stages"] for case in owner_add_dataset.cases)
    assert all("stl_extract" in case["stages"] for case in stl_extract_dataset.cases)


def test_case_messages_flattens_turns_in_order() -> None:
    case = {
        "turns": [
            {"messages": [{"role": "user", "content": "one"}]},
            {"messages": [{"role": "assistant", "content": "two"}]},
            {"messages": [{"role": "user", "content": "three"}]},
        ]
    }

    assert _case_messages(case) == [
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "two"},
        {"role": "user", "content": "three"},
    ]


def test_load_case_file_requires_stage_block(tmp_path: Path) -> None:
    case_path = tmp_path / "missing-stages.json"
    case_path.write_text(
        json.dumps(
            {
                "id": "bad-case",
                "description": "missing stage block",
                "owner": {"external_user_id": "bad"},
                "turns": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing required 'stages' block"):
        _load_case_file(case_path)
