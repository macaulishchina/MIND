"""Typed configuration schema — structure only, no file I/O."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    """A single LLM provider definition from [llm.*] in mind.toml.

    Contains everything needed to call this provider: protocol type,
    credentials, URL structure, and default model.
    """
    protocols: str = "openai"       # which code implementation to use
    template: str = ""              # inherit from another provider, e.g. "llm.openai"
    api_key: str = ""
    base_url: str = ""
    sdk_base: str = ""              # e.g. "/v1" for OpenAI SDK
    llm_suffix: str = ""            # e.g. "/chat/completions"
    embed_suffix: str = ""
    model: str = ""


class LLMConfig(BaseModel):
    """Resolved LLM configuration — ready for consumption.

    All fields are fully resolved from [llm] + [llm.{provider}].
    """
    provider: str = "openai"        # which [llm.*] entry was selected
    protocols: str = "openai"       # which code implementation to use
    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    api_key: str = ""
    base_url: str = ""
    sdk_base: str = ""
    llm_suffix: str = ""


class EmbeddingConfig(BaseModel):
    """Embedding configuration — fully independent from LLM."""
    protocols: str = "openai-embedding"
    model: str = "text-embedding-3-small"
    api_key: str = ""
    base_url: str = ""
    sdk_base: str = "/v1"
    embed_suffix: str = "/embeddings"
    dimensions: int = 1536


class VectorStoreConfig(BaseModel):
    """Vector store configuration."""
    provider: str = "qdrant"
    collection_name: str = "mind_memories"
    url: str = ""
    api_key: str = ""
    on_disk: bool = False


class HistoryStoreConfig(BaseModel):
    """SQLite history store configuration."""
    db_path: str = "mind_history.db"


class RetrievalConfig(BaseModel):
    """Retrieval parameters."""
    search_top_k: int = 5
    similarity_top_k: int = 5


class MemoryConfig(BaseModel):
    """Top-level configuration — the single output of ConfigManager.

    All fields are fully resolved. Consumers read directly, no fallback logic.
    """
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    history_store: HistoryStoreConfig = Field(default_factory=HistoryStoreConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict)