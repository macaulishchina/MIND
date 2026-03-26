"""Factory for creating embedding instances."""

from mind.config.schema import EmbeddingConfig
from mind.embeddings.base import BaseEmbedding


class EmbedderFactory:
    """Create an embedding backend based on the ``protocols`` field."""

    _protocols_map = {
        "openai-embedding": "mind.embeddings.openai.OpenAIEmbedding",
    }

    @classmethod
    def create(cls, config: EmbeddingConfig) -> BaseEmbedding:
        protocols = config.protocols.lower()
        if protocols not in cls._protocols_map:
            raise ValueError(
                f"Unsupported embedding protocol: {protocols}. "
                f"Available: {list(cls._protocols_map.keys())}"
            )

        module_path, class_name = cls._protocols_map[protocols].rsplit(".", 1)
        import importlib
        module = importlib.import_module(module_path)
        embed_class = getattr(module, class_name)
        return embed_class(config)