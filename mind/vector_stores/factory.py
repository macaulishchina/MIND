"""Factory for creating vector store instances."""

from mind.config.schema import VectorStoreConfig
from mind.vector_stores.base import BaseVectorStore


class VectorStoreFactory:
    """Create a vector store backend from configuration."""

    _provider_map = {
        "qdrant": "mind.vector_stores.qdrant.QdrantVectorStore",
        "pgvector": "mind.vector_stores.pgvector.PgVectorStore",
    }

    @classmethod
    def create(cls, config: VectorStoreConfig) -> BaseVectorStore:
        provider = config.provider.lower()
        if provider not in cls._provider_map:
            raise ValueError(
                f"Unsupported vector store provider: {provider}. "
                f"Available: {list(cls._provider_map.keys())}"
            )

        module_path, class_name = cls._provider_map[provider].rsplit(".", 1)
        import importlib
        module = importlib.import_module(module_path)
        store_class = getattr(module, class_name)
        return store_class(config)
