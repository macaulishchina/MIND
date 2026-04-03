from __future__ import annotations

from mind.config.schema import LLMConfig
from mind.llms.fake import FakeLLM
from mind.prompts import UPDATE_DECISION_USER_TEMPLATE
from mind.stl.prompt import STL_EXTRACTION_SYSTEM_PROMPT, STL_EXTRACTION_USER_TEMPLATE


def _extract_program(fake_llm: FakeLLM, conversation: str) -> str:
    return fake_llm.generate(
        messages=[
            {
                "role": "system",
                "content": STL_EXTRACTION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": STL_EXTRACTION_USER_TEMPLATE.format(
                    focus_stack="",
                    conversation=conversation,
                ),
            },
        ],
    )


def test_fake_llm_splits_atomic_self_facts_into_stl_program() -> None:
    fake_llm = FakeLLM(LLMConfig(protocols="fake", model="fake-memory-test"))

    program = _extract_program(
        fake_llm,
        "User: My name is Alice\nUser: I work at Stripe\nUser: I drink black coffee every day",
    )

    assert '$p1 = name(@self, "Alice")' in program
    assert '$p2 = work_at(@self, "Stripe")' in program
    assert '$p3 = drink(@self, "black coffee every day")' in program


def test_fake_llm_ignores_questions_in_stl_program() -> None:
    fake_llm = FakeLLM(LLMConfig(protocols="fake", model="fake-memory-test"))

    program = _extract_program(
        fake_llm,
        "User: Do you think Python is easy to learn?\nAssistant: Python is a great beginner language.",
    )

    assert program == ""


def test_fake_llm_supports_basic_chinese_stl_extraction() -> None:
    fake_llm = FakeLLM(LLMConfig(protocols="fake", model="fake-memory-test"))

    program = _extract_program(
        fake_llm,
        "User: 我叫小明，我在网易工作，我喜欢咖啡。",
    )

    assert '$p1 = name(@self, "小明")' in program
    assert '$p2 = work_at(@self, "网易")' in program
    assert '$p3 = like(@self, "咖啡")' in program


def test_fake_llm_can_emit_basic_stl_program() -> None:
    fake_llm = FakeLLM(LLMConfig(protocols="fake", model="fake-memory-test"))

    program = fake_llm.generate(
        messages=[
            {
                "role": "system",
                "content": STL_EXTRACTION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": STL_EXTRACTION_USER_TEMPLATE.format(
                    focus_stack="",
                    conversation="User: My friend Green is a football player",
                ),
            },
        ],
    )

    assert '@p1: person "green"' in program
    assert "$p1 = friend(@self, @p1)" in program
    assert "$p2 = occupation(@p1, \"football player\")" in program


def test_fake_llm_supports_generic_chat_prompt() -> None:
    fake_llm = FakeLLM(LLMConfig(protocols="fake", model="fake-memory-test"))

    response = fake_llm.generate(
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant. Reply briefly.",
            },
            {
                "role": "user",
                "content": "hi",
            },
        ],
    )

    assert response == "echo: hi"


def test_fake_llm_recognizes_decision_prompt_shape_without_exact_system_text() -> None:
    fake_llm = FakeLLM(LLMConfig(protocols="fake", model="fake-memory-test"))

    response = fake_llm.generate(
        messages=[
            {
                "role": "system",
                "content": "Decision prompt candidate variant with different wording.",
            },
            {
                "role": "user",
                "content": UPDATE_DECISION_USER_TEMPLATE.format(
                    existing_memories="[0] [self] attribute:favorite_snack=seaweed chips",
                    new_fact="[self] attribute:favorite_snack=seaweed chips",
                ),
            },
        ],
    )

    assert '"action": "NONE"' in response
