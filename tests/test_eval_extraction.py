from __future__ import annotations

import json
from pathlib import Path

from mind.config.schema import LLMConfig, LoggingConfig, MemoryConfig
from tests.eval.runners.eval_extraction import DatasetSpec
from tests.eval.runners.eval_extraction import build_report
from tests.eval.runners.eval_extraction import _configure_runner_logging
from tests.eval.runners.eval_extraction import _evaluate_case
from tests.eval.runners.eval_extraction import _load_dataset
from tests.eval.runners.eval_extraction import _resolve_dataset_paths
from tests.eval.runners.eval_extraction import _resolve_extraction_llm_cfg
from tests.eval.runners.eval_extraction import _resolve_extraction_temperature


class StaticLLM:
    def __init__(self, facts: list[dict[str, object]]) -> None:
        self._response = json.dumps({"facts": facts})

    def generate(self, messages, response_format=None, temperature=None) -> str:
        return self._response


def test_zero_extract_case_fails_no_extract_pass_when_any_fact_is_returned() -> None:
    llm = StaticLLM([
        {"text": "User likes tea", "confidence": 0.9},
    ])

    result = _evaluate_case(
        llm,
        {
            "id": "zero-001",
            "description": "zero extract case",
            "input": "User: Hello.\nAssistant: Hi.",
            "expected_facts": [],
            "should_not_extract": [],
            "expected_count_range": [0, 0],
        },
        extraction_temperature=None,
    )

    assert result.no_extract_pass is False
    assert result.count_pass is False


def test_configure_runner_logging_uses_configured_logging(monkeypatch) -> None:
    captured = {}

    def fake_setup_logging(log_cfg) -> None:
        captured["logging"] = log_cfg

    monkeypatch.setattr(
        "tests.eval.runners.eval_extraction.Memory._setup_logging",
        fake_setup_logging,
    )

    cfg = type("Cfg", (), {"logging": LoggingConfig(console=True, file="mind.log")})()

    _configure_runner_logging(cfg)

    assert captured["logging"] == cfg.logging


def test_eval_runner_prefers_extraction_stage_llm_config() -> None:
    cfg = MemoryConfig(
        llm=LLMConfig(provider="aliyun", model="base-model", temperature=0.1),
        llm_stages={
            "extraction": LLMConfig(
                provider="aliyun",
                model="extract-model",
                temperature=0.3,
            )
        },
    )

    extraction_cfg = _resolve_extraction_llm_cfg(cfg)

    assert extraction_cfg.model == "extract-model"
    assert _resolve_extraction_temperature(cfg) == 0.3


def test_relation_annotations_are_scored_from_extracted_facts() -> None:
    llm = StaticLLM([
        {"text": "My friend Green is a football player", "confidence": 0.9},
    ])

    result = _evaluate_case(
        llm,
        {
            "id": "rel-001",
            "description": "relation extraction case",
            "input": "User: My friend Green is a football player",
            "expected_facts": [
                {"match_any": ["football player"]},
            ],
            "expected_relations": [
                {"label": "friend-green", "match_all": ["friend", "Green"]},
            ],
            "forbidden_relations": [
                {"label": "boss-green", "match_all": ["boss", "Green"]},
            ],
            "expected_count_range": [1, 2],
        },
        extraction_temperature=None,
    )

    assert result.case_pass is True
    assert result.relation_hits == result.relation_total == 1
    assert result.forbidden_relation_hits == result.forbidden_relation_total == 1
    assert result.relation_case_pass is True


def test_build_report_adds_relation_metrics_only_for_relation_datasets() -> None:
    llm = StaticLLM([
        {"text": "My friend Green is a football player", "confidence": 0.9},
    ])
    case = {
        "id": "rel-002",
        "description": "relation extraction case",
        "input": "User: My friend Green is a football player",
        "expected_facts": [{"match_any": ["football player"]}],
        "expected_relations": [{"match_all": ["friend", "Green"]}],
        "expected_count_range": [1, 2],
    }
    result = _evaluate_case(llm, case, extraction_temperature=None)
    report = build_report(
        DatasetSpec(
            path=Path("tests/eval/datasets/extraction_relationship_cases.json"),
            name="extraction_relationship_cases",
            focus="relationship extraction",
            description="",
            cases=[case],
        ),
        [result],
        Path("mindt.toml"),
        {"provider": "fake", "model": "fake-memory-test", "label": "fake-fake-memory-test"},
    )

    assert "relation_recall" in report["metrics"]
    assert "relation_case_accuracy" in report["metrics"]
    assert "relation_recall" in report["targets"]


def test_default_dataset_discovery_uses_curated_top_level_extraction_datasets() -> None:
    dataset_paths = _resolve_dataset_paths(None)

    assert [path.name for path in dataset_paths] == [
        "extraction_curated_cases.json",
        "extraction_relationship_cases.json",
    ]


def test_curated_extraction_dataset_has_100_cases_without_relation_annotations() -> None:
    dataset = _load_dataset(
        Path("tests/eval/datasets/extraction_curated_cases.json")
    )

    assert dataset.name == "extraction_curated_cases"
    assert len(dataset.cases) == 100
    assert all(
        not case.get("expected_relations") and not case.get("forbidden_relations")
        for case in dataset.cases
    )


def test_relationship_extraction_dataset_has_100_relation_annotated_cases() -> None:
    dataset = _load_dataset(
        Path("tests/eval/datasets/extraction_relationship_cases.json")
    )

    assert dataset.name == "extraction_relationship_cases"
    assert len(dataset.cases) == 100
    assert all(
        case.get("expected_relations") or case.get("forbidden_relations")
        for case in dataset.cases
    )
