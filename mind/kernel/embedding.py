"""Embedding provider abstraction for dense retrieval (Phase β-1).

Provides three implementations:

* ``LocalHashEmbedding`` — deterministic hash embedding (backward-compat default).
* ``SentenceTransformerEmbedding`` — local sentence-transformers model (optional dep).
* ``OpenAIEmbedding`` — OpenAI text-embedding API.

All implementations satisfy ``EmbeddingProvider`` protocol.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from mind.kernel.retrieval import embed_text


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Minimal protocol for objects that can embed a batch of texts."""

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        """Return a list of embedding vectors, one per input text."""
        ...

    @property
    def dimension(self) -> int:
        """Return the output vector dimension."""
        ...


class LocalHashEmbedding:
    """Deterministic local hash embedding — default, zero-dependency provider.

    Produces 64-dimensional vectors using the same hash function already used
    throughout the codebase.  This is the backward-compatible provider and
    requires no external dependencies.
    """

    _dim: int = 64

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [embed_text(text) for text in texts]

    @property
    def dimension(self) -> int:
        return self._dim


class OpenAIEmbedding:
    """OpenAI text-embedding API provider.

    Requires the ``openai`` package and a valid API key.  Uses the
    ``text-embedding-3-small`` model by default (1536 dims), but this can be
    overridden via the ``model_name`` constructor argument.

    The dimension is inferred from the first API response.
    """

    def __init__(
        self,
        api_key: str,
        *,
        model_name: str = "text-embedding-3-small",
        dimension: int | None = None,
    ) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._dimension: int | None = dimension

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        try:
            import openai  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "openai package is required for OpenAIEmbedding. "
                "Install it with: pip install openai"
            ) from exc

        client = openai.OpenAI(api_key=self._api_key)
        response = client.embeddings.create(input=texts, model=self._model_name)
        vectors = [tuple(float(v) for v in item.embedding) for item in response.data]
        if vectors and self._dimension is None:
            self._dimension = len(vectors[0])
        return vectors

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            # Default for text-embedding-3-small
            return 1536
        return self._dimension


class SentenceTransformerEmbedding:
    """Local sentence-transformers embedding provider (Phase β-1).

    Requires the ``sentence-transformers`` package.  Loads the model lazily
    on first ``embed()`` call so import time is not penalised.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model: Any = None
        self._dim: int | None = None

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        model = self._load_model()
        import numpy as np  # type: ignore[import-not-found]

        embeddings: np.ndarray = model.encode(
            texts, convert_to_numpy=True, normalize_embeddings=True
        )
        if self._dim is None:
            self._dim = int(embeddings.shape[1])
        return [tuple(float(v) for v in row) for row in embeddings]

    @property
    def dimension(self) -> int:
        if self._dim is not None:
            return self._dim
        # Common default for all-MiniLM-L6-v2
        return 384

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required for SentenceTransformerEmbedding. "
                "Install with: pip install 'mind[dense]'"
            ) from exc
        self._model = SentenceTransformer(self._model_name)
        return self._model


_DEFAULT_PROVIDER: EmbeddingProvider = LocalHashEmbedding()


def get_default_provider() -> EmbeddingProvider:
    """Return the module-level default embedding provider."""
    return _DEFAULT_PROVIDER


def set_default_provider(provider: EmbeddingProvider) -> None:
    """Replace the module-level default embedding provider."""
    global _DEFAULT_PROVIDER  # noqa: PLW0603
    _DEFAULT_PROVIDER = provider


def embed_objects(
    objects: list[dict[str, Any]],
    *,
    provider: EmbeddingProvider | None = None,
) -> dict[str, tuple[float, ...]]:
    """Return a mapping from object_id to dense embedding.

    Uses ``provider`` if supplied, otherwise falls back to the module-level
    default provider (``LocalHashEmbedding`` unless overridden by
    :func:`set_default_provider`).
    """
    from mind.kernel.retrieval import build_embedding_text

    resolved = provider or _DEFAULT_PROVIDER
    texts = [build_embedding_text(obj) for obj in objects]
    vectors = resolved.embed(texts)
    return {obj["id"]: vec for obj, vec in zip(objects, vectors, strict=True)}
