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
            import openai  # type: ignore[import-untyped]
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
