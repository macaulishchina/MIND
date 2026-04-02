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
    batch_base_url: str = ""        # batch endpoint base, e.g. "https://batch.dashscope.aliyuncs.com"


class LLMConfig(BaseModel):
    """Resolved LLM configuration — ready for consumption.

    All fields are fully resolved from [llm] + [llm.{provider}].
    """
    provider: str = "openai"        # which [llm.*] entry was selected
    protocols: str = "openai"       # which code implementation to use
    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    extraction_temperature: Optional[float] = None
    api_key: str = ""
    base_url: str = ""
    sdk_base: str = ""
    llm_suffix: str = ""
    timeout: float = 120.0          # SDK timeout (seconds) for normal requests
    batch: bool = False             # global switch: route to batch endpoint
    batch_base_url: str = ""        # resolved from provider's batch_base_url
    batch_timeout: float = 3600.0   # SDK timeout (seconds) when batch is active


class LLMStageOverrideConfig(BaseModel):
    """Stage-specific LLM override before full provider resolution."""

    provider: str = ""
    model: str = ""
    temperature: Optional[float] = None
    extraction_temperature: Optional[float] = None
    batch: Optional[bool] = None
    batch_timeout: Optional[float] = None


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
    dsn: str = ""
    api_key: str = ""
    on_disk: bool = False


class HistoryStoreConfig(BaseModel):
    """SQLite history store configuration."""
    provider: str = "sqlite"
    db_path: str = "mind_history.db"
    dsn: str = ""
    table_name: str = "memory_history"


class STLStoreConfig(BaseModel):
    """Semantic Translation Layer storage configuration."""
    provider: str = "sqlite"
    db_path: str = "mind_stl.db"
    dsn: str = ""


class RetrievalConfig(BaseModel):
    """Retrieval parameters."""
    search_top_k: int = 5
    similarity_top_k: int = 5


class LoggingConfig(BaseModel):
    """Logging configuration.

    Controls console and file log output for the ``mind`` package.
    """
    level: str = "INFO"                     # DEBUG / INFO / WARNING / ERROR
    console: bool = True                    # 是否输出到控制台（stderr）
    file: str = ""                          # 日志文件路径，留空 = 不写文件
    format: str = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"

    # ── 操作日志开关 ──
    ops_llm: bool = True                    # LLM + Embedding 调用日志
    ops_vector_store: bool = True           # 向量存储操作日志
    ops_database: bool = True               # 数据库操作日志
    verbose: bool = False                   # 详细模式：显示每次操作的原始输入/输出


class ConcurrencyConfig(BaseModel):
    """Concurrency configuration for the Memory system.

    Controls the write thread pool used by ``add()`` for parallel fact
    processing, and the starvation-prevention mechanism.
    """
    max_workers: int = Field(default=8, ge=1)
    """Global write thread pool size. Also serves as the upper bound on
    concurrent LLM / embedding calls originating from ``add()``."""

    min_available_workers: int = Field(default=2, ge=0)
    """Reserved threads that a single ``add()`` call must NOT occupy.
    Prevents one large add from starving concurrent add calls.
    Effective per-add parallelism = max_workers - min_available_workers.
    Set to 0 to disable starvation protection.
    Must be strictly less than max_workers."""


class PromptsConfig(BaseModel):
    """Prompt enhancement configuration.

    Controls whether extended / supplementary prompt text is appended
    to base system prompts. Useful for trading extra tokens for better
    extraction quality on price-insensitive models.
    """
    stl_extraction_supplement: bool = False
    """Append STL_EXTRACTION_SUPPLEMENT to the STL extraction system prompt."""


class MemoryConfig(BaseModel):
    """Top-level configuration — the single output of ConfigManager.

    All fields are fully resolved. Consumers read directly, no fallback logic.
    """
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    history_store: HistoryStoreConfig = Field(default_factory=HistoryStoreConfig)
    stl_store: STLStoreConfig = Field(default_factory=STLStoreConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    concurrency: ConcurrencyConfig = Field(default_factory=ConcurrencyConfig)
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict)
    llm_stages: Dict[str, LLMConfig] = Field(default_factory=dict)
