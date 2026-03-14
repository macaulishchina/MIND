"""Shared retrieval helpers for SQLite fallback and PostgreSQL indexing."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from mind.kernel.contracts import RetrieveQueryMode
from mind.kernel.priority import effective_priority_or_base
from mind.kernel.schema import strip_control_plane_metadata

EMBEDDING_DIM = 64
_CJK_BLOCK = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
_TOKEN_PATTERN = re.compile(rf"[a-z0-9_]+|[{_CJK_BLOCK}]+", re.IGNORECASE)


@dataclass(frozen=True)
class RetrievalMatch:
    """A scored latest-object retrieval hit."""

    object: dict[str, Any]
    score: float


def build_search_text(obj: dict[str, Any]) -> str:
    """Return the canonical search text stored for keyword and vector retrieval."""

    object_id = str(obj["id"]).lower()
    public_metadata = strip_control_plane_metadata(obj["metadata"])
    return " ".join(
        [
            object_id,
            object_id.replace("-", " "),
            str(obj["type"]).lower(),
            json.dumps(obj["content"], ensure_ascii=False, sort_keys=True).lower(),
            json.dumps(public_metadata, ensure_ascii=False, sort_keys=True).lower(),
        ]
    ).strip()


def build_embedding_text(obj: dict[str, Any]) -> str:
    """Return a denser, id-weighted text basis for vector embeddings."""

    object_id = str(obj["id"]).lower()
    object_type = str(obj["type"]).lower()
    expanded_id = object_id.replace("-", " ")
    id_ngrams = " ".join(_char_ngrams(object_id))
    public_metadata = strip_control_plane_metadata(obj["metadata"])
    salient_text = _structured_text(obj["content"]) + " " + _selected_metadata_text(public_metadata)
    return " ".join(
        [
            object_id,
            object_id,
            expanded_id,
            expanded_id,
            id_ngrams,
            object_type,
            object_type,
            salient_text.lower(),
        ]
    ).strip()


def build_object_embedding(obj: dict[str, Any]) -> tuple[float, ...]:
    """Return the deterministic embedding for an object."""

    return embed_text(build_embedding_text(obj))


def build_query_embedding(query: str | dict[str, Any]) -> tuple[float, ...]:
    """Return the deterministic embedding for a retrieval query."""

    if isinstance(query, str) and query.startswith("vector:"):
        target = query.removeprefix("vector:").strip().lower()
        expanded = target.replace("-", " ")
        ngrams = " ".join(_char_ngrams(target))
        query_text = f"{target} {target} {expanded} {expanded} {ngrams}"
    else:
        query_text = canonical_query_text(query)
    return embed_text(query_text)


def canonical_query_text(query: str | dict[str, Any]) -> str:
    """Serialize retrieval query input into stable text."""

    return (
        query.lower()
        if isinstance(query, str)
        else json.dumps(query, ensure_ascii=False, sort_keys=True).lower()
    )


def latest_objects(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only the latest version for each object id."""

    latest_by_id: dict[str, dict[str, Any]] = {}
    for obj in objects:
        existing = latest_by_id.get(obj["id"])
        if existing is None or int(obj["version"]) > int(existing["version"]):
            latest_by_id[obj["id"]] = obj
    return list(latest_by_id.values())


def matches_retrieval_filters(
    obj: dict[str, Any],
    *,
    object_types: list[str],
    statuses: list[str],
    episode_id: str | None,
    task_id: str | None,
) -> bool:
    """Apply the frozen retrieval filters shared across backends."""

    if statuses:
        if obj["status"] not in statuses:
            return False
    elif obj["status"] == "invalid":
        return False

    if object_types and obj["type"] not in object_types:
        return False

    metadata = obj.get("metadata", {})

    # Phase β-4: exclude SchemaNote objects in `proposed` or `rejected` states
    # from default retrieval paths. Only `verified` and `committed` SchemaNotes
    # participate in retrieval (backward compat: absence of proposal_status is
    # treated as `committed`).
    if obj["type"] == "SchemaNote":
        proposal_status = metadata.get("proposal_status")
        if proposal_status in ("proposed", "rejected"):
            return False

    if task_id is not None and metadata.get("task_id") != task_id:
        return False

    if episode_id is None:
        return True
    if metadata.get("episode_id") == episode_id:
        return True
    if obj["id"] == episode_id:
        return True
    return episode_id in obj.get("source_refs", [])


# β-1.5: default hybrid scoring weights.
W_LEXICAL = 0.3
W_DENSE = 0.5
W_PRIORITY = 0.2


def search_objects(
    objects: list[dict[str, Any]],
    *,
    query: str | dict[str, Any],
    query_modes: list[RetrieveQueryMode],
    max_candidates: int,
    object_types: list[str],
    statuses: list[str],
    episode_id: str | None,
    task_id: str | None,
    query_embedding: tuple[float, ...] | None,
    dense_embedding: tuple[float, ...] | None = None,
    w_lexical: float = W_LEXICAL,
    w_dense: float = W_DENSE,
    w_priority: float = W_PRIORITY,
) -> list[RetrievalMatch]:
    """Run fallback retrieval scoring over in-memory latest objects.

    When *dense_embedding* is provided (from a real embedding provider) it is
    used for the dense channel; otherwise *query_embedding* (the legacy
    deterministic hash) is used with reduced weight.
    """

    filtered_objects = [
        obj
        for obj in latest_objects(objects)
        if matches_retrieval_filters(
            obj,
            object_types=object_types,
            statuses=statuses,
            episode_id=episode_id,
            task_id=task_id,
        )
    ]

    # Choose vector for dense scoring.
    effective_dense = dense_embedding or query_embedding

    matches: list[RetrievalMatch] = []
    for obj in filtered_objects:
        lexical = 0.0
        dense = 0.0

        if RetrieveQueryMode.KEYWORD in query_modes:
            lexical = keyword_score(query, obj)
        if RetrieveQueryMode.TIME_WINDOW in query_modes:
            lexical = max(lexical, time_window_score(query, obj))
        if RetrieveQueryMode.VECTOR in query_modes:
            dense = vector_score(effective_dense, obj)

        # α-2.5 / β-1.5: blended hybrid scoring
        priority_signal = effective_priority_or_base(obj)
        score = w_lexical * lexical + w_dense * dense + w_priority * priority_signal

        if score > 0:
            matches.append(RetrievalMatch(object=obj, score=score))

    matches.sort(
        key=lambda item: (item.score, item.object["updated_at"], item.object["id"]),
        reverse=True,
    )
    return matches[:max_candidates]


def keyword_score(query: str | dict[str, Any], obj: dict[str, Any]) -> float:
    """Return token-overlap keyword score."""

    query_tokens = _tokenize(canonical_query_text(query))
    if not query_tokens:
        return 0.0
    object_tokens = _tokenize(build_search_text(obj))
    overlap = len(query_tokens & object_tokens)
    if overlap == 0:
        return 0.0
    return overlap / float(len(query_tokens))


def time_window_score(query: str | dict[str, Any], obj: dict[str, Any]) -> float:
    """Return 1.0 when object created_at falls within the query window."""

    if not isinstance(query, dict):
        return 0.0
    start = query.get("start")
    end = query.get("end")
    if start is None and end is None:
        return 0.0
    try:
        created_at = _parse_iso_datetime(obj["created_at"])
    except ValueError:
        return 0.0
    if start is not None and created_at < _parse_iso_datetime(str(start)):
        return 0.0
    if end is not None and created_at > _parse_iso_datetime(str(end)):
        return 0.0
    return 1.0


def vector_score(
    query_embedding: tuple[float, ...] | None,
    obj: dict[str, Any],
) -> float:
    """Return cosine similarity between query and object embeddings."""

    if query_embedding is None:
        return 0.0
    object_embedding = build_object_embedding(obj)
    return cosine_similarity(query_embedding, object_embedding)


def embed_text(text: str) -> tuple[float, ...]:
    """Return a deterministic, normalized local embedding."""

    values = [0.0] * EMBEDDING_DIM
    tokens = _tokenize_sequence(text)
    if not tokens:
        return tuple(values)

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], byteorder="big") % EMBEDDING_DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = 1.0 + (digest[5] / 255.0)
        values[bucket] += sign * weight

    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0.0:
        return tuple(0.0 for _ in values)
    return tuple(round(value / norm, 6) for value in values)


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    """Return cosine similarity for normalized embeddings."""

    if not left or not right:
        return 0.0
    return max(0.0, round(sum(a * b for a, b in zip(left, right, strict=True)), 6))


def vector_literal(values: tuple[float, ...]) -> str:
    """Return PostgreSQL vector literal representation."""

    return "[" + ",".join(f"{value:.6f}" for value in values) + "]"


def _parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def tokenize(text: str) -> set[str]:
    """Return the canonical token set for keyword matching."""
    return set(_tokenize_sequence(text))


# Keep underscore alias for existing internal callers.
_tokenize = tokenize


def _tokenize_sequence(text: str) -> list[str]:
    normalized = text.lower()
    tokens: list[str] = []
    for token in _TOKEN_PATTERN.findall(normalized):
        if not token:
            continue
        tokens.append(token)
        if _contains_cjk(token):
            tokens.extend(_char_ngrams(token, size=2))
    return [token for token in tokens if token]


def _structured_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_structured_text(item) for item in value)
    if isinstance(value, dict):
        parts: list[str] = []
        for key in sorted(value):
            parts.append(str(key))
            parts.append(_structured_text(value[key]))
        return " ".join(part for part in parts if part)
    return str(value)


def _selected_metadata_text(metadata: dict[str, Any]) -> str:
    keys = (
        "task_id",
        "episode_id",
        "entity_name",
        "entity_kind",
        "goal",
        "result",
        "summary_scope",
        "reflection_kind",
        "claims",
        "kind",
        "relation_type",
    )
    parts: list[str] = []
    for key in keys:
        if key in metadata:
            parts.append(str(key))
            parts.append(_structured_text(metadata[key]))
    return " ".join(parts)


def _char_ngrams(text: str, size: int = 3) -> list[str]:
    normalized = text.replace(" ", "")
    if len(normalized) < size:
        return [normalized] if normalized else []
    return [normalized[index : index + size] for index in range(len(normalized) - size + 1)]


def _contains_cjk(text: str) -> bool:
    return bool(re.search(rf"[{_CJK_BLOCK}]", text))
