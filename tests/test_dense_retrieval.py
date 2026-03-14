"""Tests for Phase β-1: Dense Retrieval / Embedding Provider (test_dense_retrieval.py)."""

from __future__ import annotations

from mind.kernel.embedding import (
    EmbeddingProvider,
    LocalHashEmbedding,
    embed_objects,
    get_default_provider,
    set_default_provider,
)
from mind.kernel.retrieval import EMBEDDING_DIM, cosine_similarity, embed_text

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw_object(object_id: str = "obj-001", *, text: str = "hello world") -> dict:
    return {
        "id": object_id,
        "type": "RawRecord",
        "content": {"text": text},
        "source_refs": [],
        "created_at": "2026-03-13T12:00:00+00:00",
        "updated_at": "2026-03-13T12:00:00+00:00",
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": {
            "record_kind": "user_message",
            "episode_id": "ep-001",
            "timestamp_order": 1,
        },
    }


# ---------------------------------------------------------------------------
# β-1: EmbeddingProvider protocol
# ---------------------------------------------------------------------------


def test_local_hash_embedding_satisfies_protocol() -> None:
    """β-1: LocalHashEmbedding satisfies the EmbeddingProvider protocol."""
    provider = LocalHashEmbedding()
    assert isinstance(provider, EmbeddingProvider)


def test_local_hash_embedding_dimension() -> None:
    """β-1: LocalHashEmbedding returns EMBEDDING_DIM-dimensional vectors."""
    provider = LocalHashEmbedding()
    assert provider.dimension == EMBEDDING_DIM
    vectors = provider.embed(["hello world"])
    assert len(vectors) == 1
    assert len(vectors[0]) == EMBEDDING_DIM


def test_local_hash_embedding_batch() -> None:
    """β-1: LocalHashEmbedding handles batch inputs."""
    provider = LocalHashEmbedding()
    texts = ["hello", "world", "test query"]
    vectors = provider.embed(texts)
    assert len(vectors) == 3
    for vec in vectors:
        assert len(vec) == EMBEDDING_DIM


def test_local_hash_embedding_deterministic() -> None:
    """β-1: LocalHashEmbedding is deterministic for the same input."""
    provider = LocalHashEmbedding()
    text = "the quick brown fox"
    v1 = provider.embed([text])[0]
    v2 = provider.embed([text])[0]
    assert v1 == v2


def test_local_hash_embedding_matches_embed_text() -> None:
    """β-1: LocalHashEmbedding output matches the existing embed_text function."""
    provider = LocalHashEmbedding()
    text = "test content"
    vec = provider.embed([text])[0]
    expected = embed_text(text)
    assert vec == expected


def test_embed_objects_returns_mapping() -> None:
    """β-1: embed_objects returns a dict from object_id to embedding vector."""
    objects = [_raw_object("a", text="hello"), _raw_object("b", text="world")]
    result = embed_objects(objects)
    assert set(result.keys()) == {"a", "b"}
    for vec in result.values():
        assert len(vec) == EMBEDDING_DIM


def test_embed_objects_with_custom_provider() -> None:
    """β-1: embed_objects uses the supplied provider."""

    class FixedProvider:
        """Always returns a fixed vector."""

        def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
            return [tuple(1.0 for _ in range(8)) for _ in texts]

        @property
        def dimension(self) -> int:
            return 8

    provider = FixedProvider()
    objects = [_raw_object("x", text="anything")]
    result = embed_objects(objects, provider=provider)
    assert result["x"] == tuple(1.0 for _ in range(8))


def test_get_and_set_default_provider() -> None:
    """β-1: set_default_provider / get_default_provider round-trip."""
    original = get_default_provider()
    try:
        new_provider = LocalHashEmbedding()
        set_default_provider(new_provider)
        assert get_default_provider() is new_provider
    finally:
        set_default_provider(original)


def test_local_hash_embedding_different_texts_produce_different_vectors() -> None:
    """β-1: Different texts produce different embedding vectors."""
    provider = LocalHashEmbedding()
    v1 = provider.embed(["the quick brown fox"])[0]
    v2 = provider.embed(["a completely different sentence"])[0]
    # They should not be identical
    assert v1 != v2


def test_similar_texts_have_higher_cosine_similarity() -> None:
    """β-1: Semantically similar texts should have higher cosine similarity."""
    provider = LocalHashEmbedding()
    sim_texts = ["memory system for AI", "memory system for LLMs"]
    diff_texts = ["memory system for AI", "cooking recipes for dinner"]
    v_sim_a, v_sim_b = provider.embed(sim_texts)
    v_diff_a, v_diff_b = provider.embed(diff_texts)
    sim_score = cosine_similarity(v_sim_a, v_sim_b)
    diff_score = cosine_similarity(v_diff_a, v_diff_b)
    # Similar texts should be more similar than dissimilar texts.
    assert sim_score >= diff_score
