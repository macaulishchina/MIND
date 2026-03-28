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


def test_extract_facts_filters_operational_noise_and_external_advice() -> None:
    llm = CaptureLLM(
        json.dumps(
            {
                "facts": [
                    {"text": "User retried the command three times", "confidence": 0.8},
                    {"text": "User encountered a timeout error", "confidence": 0.8},
                    {"text": "User uses zsh every day", "confidence": 0.9},
                    {
                        "text": "User's manager wants the user to write more Rust",
                        "confidence": 1.0,
                    },
                    {"text": "User mostly writes Python", "confidence": 1.0},
                ]
            }
        )
    )

    facts = Memory._extract_facts(llm, "User: test")

    assert facts == [
        {"text": "User uses zsh every day", "confidence": 0.9},
        {"text": "User mostly writes Python", "confidence": 1.0},
    ]


def test_extract_facts_filters_speculation_but_keeps_committed_future_plan() -> None:
    llm = CaptureLLM(
        json.dumps(
            {
                "facts": [
                    {"text": "User currently lives in Hangzhou", "confidence": 1.0},
                    {"text": "User might move to Singapore next year", "confidence": 0.4},
                    {"text": "User is moving to Berlin next month", "confidence": 1.0},
                    {
                        "text": "User has already signed a lease for the move",
                        "confidence": 1.0,
                    },
                ]
            }
        )
    )

    facts = Memory._extract_facts(llm, "User: test")

    assert facts == [
        {"text": "User currently lives in Hangzhou", "confidence": 1.0},
        {"text": "User is moving to Berlin next month", "confidence": 1.0},
        {"text": "User has already signed a lease for the move", "confidence": 1.0},
    ]


def test_extract_facts_keeps_stable_deployment_fact() -> None:
    llm = CaptureLLM(
        json.dumps(
            {
                "facts": [
                    {"text": "User deploys to Kubernetes", "confidence": 1.0},
                ]
            }
        )
    )

    facts = Memory._extract_facts(llm, "User: test")

    assert facts == [{"text": "User deploys to Kubernetes", "confidence": 1.0}]


def test_extract_facts_canonicalizes_preference_like_facts() -> None:
    llm = CaptureLLM(
        json.dumps(
            {
                "facts": [
                    {"text": "User prefers replies to be terse", "confidence": 1.0},
                    {
                        "text": "User prefers that responses use lists where appropriate",
                        "confidence": 1.0,
                    },
                    {
                        "text": "User requests summaries to be in English",
                        "confidence": 1.0,
                    },
                    {"text": "User typically uses Chinese", "confidence": 1.0},
                ]
            }
        )
    )

    facts = Memory._extract_facts(llm, "User: test")

    assert facts == [
        {"text": "User prefers concise answers", "confidence": 1.0},
        {"text": "User prefers list-form responses", "confidence": 1.0},
        {"text": "User prefers summaries in English", "confidence": 1.0},
        {"text": "User usually uses Chinese", "confidence": 1.0},
    ]


def test_extract_facts_canonicalizes_negated_drink_update() -> None:
    llm = CaptureLLM(
        json.dumps(
            {
                "facts": [
                    {"text": "User does not drink coffee anymore", "confidence": 1.0},
                ]
            }
        )
    )

    facts = Memory._extract_facts(llm, "User: test")

    assert facts == [{"text": "User no longer drinks coffee", "confidence": 1.0}]


def test_extract_facts_filters_weak_language_inference() -> None:
    llm = CaptureLLM(
        json.dumps(
            {
                "facts": [
                    {"text": "User's primary language appears to be Chinese", "confidence": 0.6},
                    {"text": "User usually uses Chinese", "confidence": 1.0},
                ]
            }
        )
    )

    facts = Memory._extract_facts(llm, "User: test")

    assert facts == [{"text": "User usually uses Chinese", "confidence": 1.0}]
