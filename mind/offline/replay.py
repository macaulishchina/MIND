"""Replay target ranking and reuse metrics."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from mind.fixtures.long_horizon_dev import LongHorizonStep
from mind.kernel.store import MemoryStore


@dataclass(frozen=True)
class ReplayTarget:
    object_id: str
    score: float


def select_replay_targets(
    store: MemoryStore,
    candidate_ids: tuple[str, ...],
    *,
    top_k: int,
) -> tuple[ReplayTarget, ...]:
    """Select the highest-priority replay candidates from a fixed pool."""

    scored_targets: list[ReplayTarget] = []
    for object_id in candidate_ids:
        if store.is_object_concealed(object_id):
            continue
        obj = store.read_object(object_id)
        scored_targets.append(
            ReplayTarget(
                object_id=object_id,
                score=_replay_score(obj),
            )
        )
    scored_targets.sort(key=lambda item: (item.score, item.object_id), reverse=True)
    return tuple(scored_targets[:top_k])


def deterministic_random_decile(
    sequence_id: str,
    candidate_ids: tuple[str, ...],
    *,
    top_k: int,
) -> tuple[str, ...]:
    """Return a deterministic random-looking baseline sample from a candidate pool."""

    ranked_ids = sorted(
        candidate_ids,
        key=lambda object_id: _stable_hash(f"{sequence_id}:{object_id}"),
    )
    return tuple(ranked_ids[:top_k])


def future_reuse_rate(selected_ids: tuple[str, ...], steps: tuple[LongHorizonStep, ...]) -> float:
    """Return per-step future reuse density for selected replay targets."""

    if not selected_ids:
        return 0.0
    future_mentions = 0
    selected = set(selected_ids)
    for step in steps:
        future_mentions += sum(object_id in selected for object_id in step.needed_object_ids)
    max_mentions = len(selected_ids) * len(steps)
    if max_mentions <= 0:
        return 0.0
    return round(future_mentions / float(max_mentions), 4)


def _replay_score(obj: dict[str, Any]) -> float:
    priority = float(obj["priority"])
    object_type = str(obj["type"])
    metadata = obj.get("metadata", {})
    score = priority

    if object_type == "ReflectionNote":
        score += 0.70
        if metadata.get("reflection_kind") == "failure":
            score += 0.25
    elif object_type == "SummaryNote":
        score += 0.45
    elif object_type == "SchemaNote":
        score += 0.40
    elif object_type == "TaskEpisode":
        score += 0.10
    elif object_type == "RawRecord":
        score -= 0.05

    claims = metadata.get("claims", [])
    if isinstance(claims, list) and "stale-memory" in claims:
        score += 0.10

    # α-2: dynamic signal adjustments from access and feedback counters
    access_count = metadata.get("access_count", 0)
    if isinstance(access_count, int | float) and access_count > 0:
        score += min(0.20, 0.02 * float(access_count))

    feedback_positive = metadata.get("feedback_positive_count", 0)
    feedback_negative = metadata.get("feedback_negative_count", 0)
    if isinstance(feedback_positive, int | float) and feedback_positive > 0:
        score += min(0.15, 0.05 * float(feedback_positive))
    if isinstance(feedback_negative, int | float) and feedback_negative > 0:
        score -= min(0.15, 0.05 * float(feedback_negative))

    decay_score = metadata.get("decay_score")
    if isinstance(decay_score, int | float):
        score -= (1.0 - float(decay_score)) * 0.10

    return round(score, 4)


def _stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
