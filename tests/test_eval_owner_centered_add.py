from __future__ import annotations

import json
from pathlib import Path

from mind.config.manager import _DEFAULT_TEST_TOML
from mind.memory import Memory
from tests.eval.runners.eval_owner_centered_add import DatasetSpec
from tests.eval.runners.eval_owner_centered_add import build_report
from tests.eval.runners.eval_owner_centered_add import build_summary
from tests.eval.runners.eval_owner_centered_add import _case_messages
from tests.eval.runners.eval_owner_centered_add import _case_owner_lookup
from tests.eval.runners.eval_owner_centered_add import _evaluate_case
from tests.eval.runners.eval_owner_centered_add import _evaluate_dataset_cases
from tests.eval.runners.eval_owner_centered_add import _eval_config
from tests.eval.runners.eval_owner_centered_add import _load_dataset


CASES_DIR = Path("tests/eval/cases")


def test_add_suite_loads() -> None:
    dataset = _load_dataset(CASES_DIR)

    assert dataset.name == "cases"
    assert len(dataset.cases) == 18


def test_feature_suite_loads() -> None:
    dataset = _load_dataset(CASES_DIR)
    feature_cases = [c for c in dataset.cases if c["id"].startswith("owner-feature-")]

    assert len(feature_cases) == 4


def test_relationship_suite_loads() -> None:
    dataset = _load_dataset(CASES_DIR)
    rel_cases = [c for c in dataset.cases if c["id"].startswith("owner-rel-")]

    assert len(rel_cases) == 8


def test_case_owner_lookup_supports_known_and_anonymous_owners() -> None:
    assert _case_owner_lookup(
        {"owner": {"external_user_id": "alice"}}
    ) == "alice"
    assert _case_owner_lookup(
        {"owner": {"anonymous_session_id": "anon-1"}}
    ) == "anon-1"


def test_owner_centered_eval_case_passes_for_chunk_final_state(memory_config) -> None:
    dataset = _load_dataset(CASES_DIR)
    update_case = next(case for case in dataset.cases if case["id"] == "owner-add-005")

    result = _evaluate_case(memory_config, update_case)

    assert result.case_pass is True
    assert result.count_pass is True
    assert result.owner_pass is True
    assert result.failures == []


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


def test_owner_centered_eval_calls_memory_add_once_per_case(memory_config, monkeypatch) -> None:
    dataset = _load_dataset(CASES_DIR)
    case = next(case for case in dataset.cases if case["id"] == "owner-add-005")
    calls: list[list[dict[str, str]]] = []
    original_add = Memory.add

    def wrapped_add(self, *args, **kwargs):
        calls.append(kwargs["messages"])
        return original_add(self, *args, **kwargs)

    monkeypatch.setattr(Memory, "add", wrapped_add)

    result = _evaluate_case(memory_config, case)

    assert result.case_pass is True
    assert len(calls) == 1
    assert calls[0] == _case_messages(case)


def test_memory_config_forces_all_llm_stages_to_fake(memory_config) -> None:
    assert memory_config.llm.provider == "fake"
    assert set(memory_config.llm_stages) == {"decision", "stl_extraction"}
    assert all(stage.provider == "fake" for stage in memory_config.llm_stages.values())


def test_owner_centered_report_and_summary_render(tmp_path, memory_config) -> None:
    dataset = _load_dataset(CASES_DIR)
    # Exclude comprehensive cases — they require real LLM for meaningful results
    smoke_dataset = DatasetSpec(
        path=dataset.path,
        name=dataset.name,
        cases=[c for c in dataset.cases if not c["id"].startswith("owner-comprehensive-")],
    )
    case_results = _evaluate_dataset_cases(memory_config, smoke_dataset, concurrency=2)

    report = build_report(smoke_dataset, case_results, _DEFAULT_TEST_TOML)
    output_path = tmp_path / "owner_centered_report.json"
    output_path.write_text(json.dumps(report), encoding="utf-8")
    summary = build_summary(report, output_path)

    assert report["metrics"]["case_pass_rate"] == 1.0
    assert report["metrics"]["canonical_text_accuracy"] == 1.0
    assert "update_accuracy" not in report["metrics"]
    assert "Owner-Centered Add Evaluation Summary" in summary


def test_owner_centered_feature_dataset_cases_pass(memory_config) -> None:
    dataset = _load_dataset(CASES_DIR)
    feature_dataset = DatasetSpec(
        path=dataset.path,
        name=dataset.name,
        cases=[c for c in dataset.cases if c["id"].startswith("owner-feature-")],
    )

    case_results = _evaluate_dataset_cases(memory_config, feature_dataset, concurrency=2)

    assert all(result.case_pass for result in case_results)


def test_owner_centered_relationship_representative_cases_pass(memory_config) -> None:
    dataset = _load_dataset(CASES_DIR)
    selected_ids = {
        "owner-rel-inverse-001",
        "owner-rel-stable-001",
        "owner-rel-split-001",
        "owner-rel-owner-002",
    }
    selected_dataset = DatasetSpec(
        path=dataset.path,
        name=dataset.name,
        cases=[case for case in dataset.cases if case["id"] in selected_ids],
    )

    case_results = _evaluate_dataset_cases(memory_config, selected_dataset, concurrency=2)

    assert len(case_results) == len(selected_ids)
    assert all(result.case_pass for result in case_results)


def test_owner_centered_dataset_concurrency_preserves_case_order(memory_config) -> None:
    dataset = _load_dataset(CASES_DIR)
    smoke_dataset = DatasetSpec(
        path=dataset.path,
        name=dataset.name,
        cases=[c for c in dataset.cases if not c["id"].startswith("owner-comprehensive-")],
    )

    case_results = _evaluate_dataset_cases(memory_config, smoke_dataset, concurrency=3)

    assert [result.case_id for result in case_results] == [
        case["id"] for case in smoke_dataset.cases
    ]
    assert all(result.case_pass for result in case_results)


def test_eval_config_forces_isolated_local_vector_store(memory_config, tmp_path) -> None:
    memory_config.vector_store.provider = "pgvector"
    memory_config.vector_store.dsn = "postgresql://example"
    memory_config.logging.console = True
    memory_config.logging.file = "mind.log"

    eval_cfg = _eval_config(memory_config, "owner-add-001", str(tmp_path))

    assert eval_cfg.vector_store.provider == "qdrant"
    assert eval_cfg.vector_store.url == ""
    assert eval_cfg.vector_store.dsn == ""
    assert eval_cfg.vector_store.on_disk is False
    assert eval_cfg.logging.console is True
    assert eval_cfg.logging.file == "mind.log"


def test_load_single_case_file() -> None:
    case_path = CASES_DIR / "owner-add-001.json"
    dataset = _load_dataset(case_path)
    assert len(dataset.cases) == 1
    assert dataset.cases[0]["id"] == "owner-add-001"


def test_single_case_file_passes(memory_config) -> None:
    case_path = CASES_DIR / "owner-add-001.json"
    dataset = _load_dataset(case_path)
    case_results = _evaluate_dataset_cases(memory_config, dataset)
    assert len(case_results) == 1
    assert case_results[0].case_pass is True
