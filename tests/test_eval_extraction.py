from __future__ import annotations

import json

from mind.config.schema import LoggingConfig
from tests.eval.runners.eval_extraction import _configure_runner_logging
from tests.eval.runners.eval_extraction import _evaluate_case


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