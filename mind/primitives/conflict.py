"""Input conflict detection for memory writes (Phase β-2).

Classifies the relationship between a newly written object and its nearest
neighbours in the memory store.

Relations:

* ``DUPLICATE`` — near-identical content (cosine similarity > 0.95).
* ``REFINE`` — overlapping but incremental update (> 0.85).
* ``CONTRADICT`` — content contains strong negation signals.
* ``SUPERSEDE`` — explicit temporal supersession signal.
* ``NOVEL`` — no significant overlap found.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mind.kernel.store import MemoryStore

# Keywords that suggest contradiction / negation.
_NEGATION_KEYWORDS = frozenset(
    {
        "not",
        "no",
        "never",
        "incorrect",
        "wrong",
        "false",
        "invalid",
        "contradict",
        "deny",
        "denied",
        "opposite",
        "unlike",
        "disagree",
        "doesn't",
        "don't",
        "won't",
        "isn't",
        "wasn't",
        "weren't",
    }
)

_SUPERSEDE_KEYWORDS = frozenset(
    {
        "supersede",
        "replace",
        "replaced",
        "outdated",
        "deprecated",
        "update",
        "updated",
        "new version",
        "previously",
    }
)


class ConflictRelation(StrEnum):
    """Relationship category between a new object and an existing neighbour."""

    DUPLICATE = "duplicate"
    REFINE = "refine"
    CONTRADICT = "contradict"
    SUPERSEDE = "supersede"
    NOVEL = "novel"


@dataclass(frozen=True)
class ConflictDetectionResult:
    """Result of comparing a new object against one existing neighbour."""

    relation: ConflictRelation
    confidence: float
    neighbor_id: str
    explanation: str


def detect_conflicts(
    store: MemoryStore,
    new_object: dict[str, Any],
    *,
    top_k: int = 3,
) -> list[ConflictDetectionResult]:
    """Detect conflicts between *new_object* and its nearest neighbours.

    Retrieves up to *top_k* existing objects of the same type using the store's
    search interface, then applies rule-based classification to each pair.

    Args:
        store: The memory store to search for neighbours.
        new_object: The freshly written object (must include ``id``, ``type``,
            ``content``, and ``metadata`` fields).
        top_k: Maximum number of neighbours to compare against.

    Returns:
        A list of :class:`ConflictDetectionResult`, one per relevant neighbour.
        Objects classified as ``NOVEL`` are included only when the list would
        otherwise be empty.
    """
    from mind.kernel.retrieval import (
        build_embedding_text,
        build_query_embedding,
        cosine_similarity,
        search_objects,
    )
    from mind.primitives.contracts import RetrieveQueryMode

    query_text = build_embedding_text(new_object)
    query_embedding = build_query_embedding(query_text)

    # Search for nearest neighbours (same type or all types).
    all_objects = list(store.iter_latest_objects())
    # Exclude the new object itself.
    candidates = [
        obj
        for obj in all_objects
        if obj["id"] != new_object["id"] and obj.get("status") == "active"
    ]

    matches = search_objects(
        candidates,
        query=query_text,
        query_modes=[RetrieveQueryMode.KEYWORD, RetrieveQueryMode.VECTOR],
        max_candidates=top_k,
        object_types=[],
        statuses=["active"],
        episode_id=None,
        task_id=None,
        query_embedding=query_embedding,
    )

    if not matches:
        return []

    results: list[ConflictDetectionResult] = []
    new_embedding = query_embedding
    new_content_text = _content_text(new_object)

    for match in matches:
        neighbour = match.object
        neighbour_text = build_embedding_text(neighbour)
        neighbour_embedding = build_query_embedding(neighbour_text)
        similarity = cosine_similarity(new_embedding, neighbour_embedding)

        relation, confidence, explanation = _classify(
            similarity=similarity,
            new_content_text=new_content_text,
            neighbour_content_text=_content_text(neighbour),
            new_object=new_object,
            neighbour=neighbour,
        )
        results.append(
            ConflictDetectionResult(
                relation=relation,
                confidence=confidence,
                neighbor_id=neighbour["id"],
                explanation=explanation,
            )
        )

    # Filter out NOVEL results unless that's all we have.
    non_novel = [r for r in results if r.relation is not ConflictRelation.NOVEL]
    return non_novel if non_novel else results


def _classify(
    *,
    similarity: float,
    new_content_text: str,
    neighbour_content_text: str,
    new_object: dict[str, Any],
    neighbour: dict[str, Any],
) -> tuple[ConflictRelation, float, str]:
    """Rule-based relation classification for a single pair."""

    combined_text = (new_content_text + " " + neighbour_content_text).lower()
    has_negation = any(kw in combined_text for kw in _NEGATION_KEYWORDS)
    has_supersede = any(kw in combined_text for kw in _SUPERSEDE_KEYWORDS)

    if similarity > 0.95:
        return (
            ConflictRelation.DUPLICATE,
            round(similarity, 4),
            f"near-identical content (cosine={similarity:.3f})",
        )

    if has_supersede:
        return (
            ConflictRelation.SUPERSEDE,
            round(0.75 + similarity * 0.25, 4),
            "supersession keywords detected",
        )

    if has_negation and similarity > 0.5:
        confidence = round(0.6 + similarity * 0.3, 4)
        return (
            ConflictRelation.CONTRADICT,
            confidence,
            f"negation keywords detected with overlap (cosine={similarity:.3f})",
        )

    if similarity > 0.85:
        return (
            ConflictRelation.REFINE,
            round(similarity, 4),
            f"incremental refinement (cosine={similarity:.3f})",
        )

    return (
        ConflictRelation.NOVEL,
        round(1.0 - similarity, 4),
        f"no significant overlap (cosine={similarity:.3f})",
    )


def _content_text(obj: dict[str, Any]) -> str:
    """Return a flat text representation of an object's content."""
    import json

    content = obj.get("content", {})
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, sort_keys=True)
