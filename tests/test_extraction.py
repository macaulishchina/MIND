from __future__ import annotations

import json

from mind.memory import Memory


class CaptureLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = []

    def generate(self, messages, response_format=None, temperature=None) -> str:
        self.calls.append(
            {
                "messages": messages,
                "response_format": response_format,
                "temperature": temperature,
            }
        )
        return self.response


def test_extract_facts_normalizes_and_deduplicates() -> None:
    llm = CaptureLLM(
        json.dumps(
            {
                "facts": [
                    {"text": "  User likes black coffee.  ", "confidence": "0.7"},
                    {"text": "User likes black coffee", "confidence": 0.9},
                    {"text": "", "confidence": 0.8},
                    {"text": "User works at Stripe!!!", "confidence": 1.3},
                    {"text": "User owns a bike", "confidence": "bad-value"},
                    "not-a-dict",
                ]
            }
        )
    )

    facts = Memory._extract_facts(llm, "User: test")

    assert facts == [
        {"text": "User likes black coffee", "confidence": 0.9},
        {"text": "User works at Stripe", "confidence": 1.0},
        {"text": "User owns a bike", "confidence": 0.5},
    ]
    assert llm.calls[0]["response_format"] == {"type": "json_object"}


def test_extract_facts_uses_temperature_override() -> None:
    llm = CaptureLLM(json.dumps({"facts": [{"text": "User likes tea", "confidence": 0.8}]}))

    facts = Memory._extract_facts(llm, "User: I like tea", temperature=0.15)

    assert facts == [{"text": "User likes tea", "confidence": 0.8}]
    assert llm.calls[0]["temperature"] == 0.15


def test_normalize_fact_text_trims_whitespace_and_punctuation() -> None:
    assert Memory._normalize_fact_text("  User likes tea... \n") == "User likes tea"
    assert Memory._normalize_fact_text(None) == ""


def test_extract_facts_keeps_third_party_and_operational_statements() -> None:
    llm = CaptureLLM(
        json.dumps(
            {
                "facts": [
                    {
                        "text": "User's friend Green is a football player",
                        "confidence": 1.0,
                    },
                    {"text": "User retried the command three times", "confidence": 0.8},
                    {
                        "text": "User's manager wants the migration finished this week",
                        "confidence": 0.9,
                    },
                ]
            }
        )
    )

    facts = Memory._extract_facts(llm, "User: test")

    assert facts == [
        {"text": "User's friend Green is a football player", "confidence": 1.0},
        {"text": "User retried the command three times", "confidence": 0.8},
        {
            "text": "User's manager wants the migration finished this week",
            "confidence": 0.9,
        },
    ]


def test_build_canonical_text_uses_structured_tag_style() -> None:
    canonical = Memory._build_canonical_text(
        subject_ref="friend:green",
        field_key="occupation",
        field_value_json={"value": "football player"},
    )

    assert canonical == "[friend:green] occupation=football player"


def test_normalize_name_casefolds_and_collapses_whitespace() -> None:
    assert Memory._normalize_name("  Green  ") == "green"
    assert Memory._normalize_name("GrEeN\tSmith") == "green smith"
