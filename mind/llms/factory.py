"""Factory for creating LLM instances."""

from mind.config.schema import LLMConfig
from mind.llms.base import BaseLLM


class LlmFactory:
    """Create an LLM backend based on the ``protocols`` field.

    The ``protocols`` field determines which code implementation to use.
    Multiple providers can share the same protocol (e.g. deepseek uses "openai").
    """

    _protocols_map = {
        "openai": "mind.llms.openai.OpenAILLM",
        "anthropic": "mind.llms.anthropic.AnthropicLLM",
        "google": "mind.llms.google.GoogleLLM",
        "fake": "mind.llms.fake.FakeLLM",
    }

    @classmethod
    def create(cls, config: LLMConfig) -> BaseLLM:
        protocols = config.protocols.lower()
        if protocols not in cls._protocols_map:
            raise ValueError(
                f"Unsupported LLM protocol: {protocols}. "
                f"Available: {list(cls._protocols_map.keys())}"
            )

        module_path, class_name = cls._protocols_map[protocols].rsplit(".", 1)
        import importlib
        module = importlib.import_module(module_path)
        llm_class = getattr(module, class_name)
        return llm_class(config)