from __future__ import annotations

import json

from mind.config.schema import LLMConfig
from mind.llms.fake import FakeLLM
from mind.prompts import FACT_EXTRACTION_SYSTEM_PROMPT, FACT_EXTRACTION_USER_TEMPLATE


def _extract(fake_llm: FakeLLM, conversation: str) -> list[dict[str, object]]:
    response = fake_llm.generate(
        messages=[
            {
                "role": "system",
                "content": FACT_EXTRACTION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": FACT_EXTRACTION_USER_TEMPLATE.format(
                    conversation=conversation,
                ),
            },
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(response)["facts"]


def test_fake_llm_splits_atomic_facts() -> None:
    fake_llm = FakeLLM(LLMConfig(protocols="fake", model="fake-memory-test"))

    facts = _extract(
        fake_llm,
        "User: My name is Alice, I work at Stripe, and I drink black coffee every day.",
    )

    texts = [fact["text"] for fact in facts]
    assert any("Alice" in text for text in texts)
    assert any("Stripe" in text for text in texts)
    assert any("black coffee" in text for text in texts)


def test_fake_llm_filters_questions_and_troubleshooting_noise() -> None:
    fake_llm = FakeLLM(LLMConfig(protocols="fake", model="fake-memory-test"))

    question_facts = _extract(
        fake_llm,
        "User: Do you think Python is easy to learn?\nAssistant: Python is a great beginner language.",
    )
    troubleshooting_facts = _extract(
        fake_llm,
        "User: 我刚才重试了三次命令，还是报错超时。\nAssistant: 先重启服务试试。",
    )

    assert question_facts == []
    assert troubleshooting_facts == []


def test_fake_llm_supports_basic_chinese_fact_splitting() -> None:
    fake_llm = FakeLLM(LLMConfig(protocols="fake", model="fake-memory-test"))

    facts = _extract(
        fake_llm,
        "User: 我之前在网易做后端，现在在字节做AI。",
    )

    texts = [fact["text"] for fact in facts]
    assert any("之前在网易" in text for text in texts)
    assert any("现在在字节" in text for text in texts)