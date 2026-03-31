from __future__ import annotations

import logging
from pathlib import Path

import pytest

from mind.config.schema import LLMConfig, LoggingConfig
from mind.llms.fake import FakeLLM
from mind.ops_logger import ops
from mind.runtime_logging import configure_runtime_logging
from tests.eval.runners.eval_llm_speed import main as eval_llm_speed_main


@pytest.fixture(autouse=True)
def restore_mind_logging():
    mind_logger = logging.getLogger("mind")
    original_handlers = list(mind_logger.handlers)
    original_level = mind_logger.level
    original_propagate = mind_logger.propagate
    original_switches = (
        ops._sw.llm,
        ops._sw.vector_store,
        ops._sw.database,
        ops._sw.verbose,
    )

    yield

    for handler in list(mind_logger.handlers):
        mind_logger.removeHandler(handler)
        if handler not in original_handlers:
            try:
                handler.close()
            except Exception:
                pass
    for handler in original_handlers:
        mind_logger.addHandler(handler)
    mind_logger.setLevel(original_level)
    mind_logger.propagate = original_propagate
    ops.configure(
        ops_llm=original_switches[0],
        ops_vector_store=original_switches[1],
        ops_database=original_switches[2],
        verbose=original_switches[3],
    )


def _fake_chat_messages() -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "You are a helpful assistant. Reply briefly."},
        {"role": "user", "content": "hi"},
    ]


def test_configure_runtime_logging_emits_verbose_llm_detail(capsys) -> None:
    configure_runtime_logging(
        LoggingConfig(console=True, file="", format="%(message)s", verbose=True)
    )
    fake_llm = FakeLLM(LLMConfig(provider="fake", protocols="fake", model="fake-memory-test"))

    response = fake_llm.generate(messages=_fake_chat_messages())
    captured = capsys.readouterr()

    assert response == "echo: hi"
    assert "🧠 [LLM]" in captured.err
    assert "[user]" in captured.err
    assert "[response]" in captured.err


def test_configure_runtime_logging_refreshes_ops_switches(capsys) -> None:
    fake_llm = FakeLLM(LLMConfig(provider="fake", protocols="fake", model="fake-memory-test"))

    configure_runtime_logging(
        LoggingConfig(
            console=True,
            file="",
            format="%(message)s",
            ops_llm=False,
            verbose=True,
        )
    )
    fake_llm.generate(messages=_fake_chat_messages())
    first = capsys.readouterr()

    configure_runtime_logging(
        LoggingConfig(
            console=True,
            file="",
            format="%(message)s",
            ops_llm=True,
            verbose=True,
        )
    )
    fake_llm.generate(messages=_fake_chat_messages())
    second = capsys.readouterr()

    assert "🧠 [LLM]" not in first.err
    assert "🧠 [LLM]" in second.err
    assert "[response]" in second.err


def test_eval_llm_speed_initializes_logging_from_toml(tmp_path: Path, capsys) -> None:
    toml_path = tmp_path / "speed.toml"
    toml_path.write_text(
        """
[llm]
provider = "fake"
temperature = 0.0
batch = false

[llm.fake]
protocols = "fake"
model = "fake-memory-test"

[logging]
level = "INFO"
console = true
file = ""
format = "%(message)s"
ops_llm = true
ops_vector_store = true
ops_database = true
verbose = true
""".strip(),
        encoding="utf-8",
    )

    exit_code = eval_llm_speed_main(
        [
            "--toml",
            str(toml_path),
            "--stage",
            "llm",
            "--text",
            "hi",
            "--runs",
            "1",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "run 1/1:" in captured.out
    assert "🧠 [LLM]" in captured.err
    assert "[user]" in captured.err
    assert "[response]" in captured.err
