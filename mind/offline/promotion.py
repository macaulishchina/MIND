"""Promotion policy helpers for offline maintenance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: PolicyNote / PreferenceNote promotions require convergent evidence from at
#: least this many distinct episodes (higher threshold than SchemaNote).
POLICY_PROMOTION_MIN_EPISODES = 3
PREFERENCE_PROMOTION_MIN_EPISODES = 3


@dataclass(frozen=True)
class PromotionDecision:
    """Promotion decision derived from a candidate object set."""

    promote: bool
    reason: str
    supporting_episode_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    stability_score: float


def assess_schema_promotion(target_objects: list[dict[str, Any]]) -> PromotionDecision:
    """Return whether a set of objects should be promoted into a SchemaNote."""

    if len(target_objects) < 2:
        return PromotionDecision(
            promote=False,
            reason="promotion requires at least two source objects",
            supporting_episode_ids=(),
            evidence_refs=tuple(obj["id"] for obj in target_objects),
            stability_score=0.0,
        )

    if any(obj["status"] != "active" for obj in target_objects):
        return PromotionDecision(
            promote=False,
            reason="promotion candidates must all be active",
            supporting_episode_ids=(),
            evidence_refs=tuple(obj["id"] for obj in target_objects),
            stability_score=0.0,
        )

    episode_ids = sorted(
        {
            str(obj.get("metadata", {}).get("episode_id"))
            for obj in target_objects
            if obj.get("metadata", {}).get("episode_id")
        }
    )
    if len(episode_ids) < 2:
        return PromotionDecision(
            promote=False,
            reason="promotion requires cross-episode support",
            supporting_episode_ids=tuple(episode_ids),
            evidence_refs=tuple(obj["id"] for obj in target_objects),
            stability_score=0.0,
        )

    conflict_tags = {
        str(obj.get("metadata", {}).get("reflection_kind"))
        for obj in target_objects
        if obj["type"] == "ReflectionNote" and obj.get("metadata", {}).get("reflection_kind")
    }
    if {"success", "failure"} <= conflict_tags:
        return PromotionDecision(
            promote=False,
            reason="promotion candidates contain conflicting reflection outcomes",
            supporting_episode_ids=tuple(episode_ids),
            evidence_refs=tuple(obj["id"] for obj in target_objects),
            stability_score=0.0,
        )

    stability_score = round(
        min(0.95, 0.45 + 0.10 * len(target_objects) + 0.10 * len(episode_ids)),
        4,
    )
    return PromotionDecision(
        promote=True,
        reason=(
            "cross-episode support from "
            f"{len(target_objects)} objects across {len(episode_ids)} episodes"
        ),
        supporting_episode_ids=tuple(episode_ids),
        evidence_refs=tuple(obj["id"] for obj in target_objects),
        stability_score=stability_score,
    )


def assess_policy_promotion(target_objects: list[dict[str, Any]]) -> PromotionDecision:
    """Return whether a set of objects should be promoted into a PolicyNote.

    Requires convergent evidence from at least
    :data:`POLICY_PROMOTION_MIN_EPISODES` distinct episodes — a higher bar than
    SchemaNote promotion.
    """
    if len(target_objects) < 2:
        return PromotionDecision(
            promote=False,
            reason="policy promotion requires at least two source objects",
            supporting_episode_ids=(),
            evidence_refs=tuple(obj["id"] for obj in target_objects),
            stability_score=0.0,
        )

    if any(obj["status"] != "active" for obj in target_objects):
        return PromotionDecision(
            promote=False,
            reason="policy promotion candidates must all be active",
            supporting_episode_ids=(),
            evidence_refs=tuple(obj["id"] for obj in target_objects),
            stability_score=0.0,
        )

    episode_ids = sorted(
        {
            str(obj.get("metadata", {}).get("episode_id"))
            for obj in target_objects
            if obj.get("metadata", {}).get("episode_id")
        }
    )
    if len(episode_ids) < POLICY_PROMOTION_MIN_EPISODES:
        return PromotionDecision(
            promote=False,
            reason=(
                f"policy promotion requires at least {POLICY_PROMOTION_MIN_EPISODES} "
                f"distinct episodes; found {len(episode_ids)}"
            ),
            supporting_episode_ids=tuple(episode_ids),
            evidence_refs=tuple(obj["id"] for obj in target_objects),
            stability_score=0.0,
        )

    stability_score = round(
        min(0.95, 0.50 + 0.10 * len(target_objects) + 0.05 * len(episode_ids)),
        4,
    )
    return PromotionDecision(
        promote=True,
        reason=(
            "policy convergence from "
            f"{len(target_objects)} objects across {len(episode_ids)} episodes"
        ),
        supporting_episode_ids=tuple(episode_ids),
        evidence_refs=tuple(obj["id"] for obj in target_objects),
        stability_score=stability_score,
    )


def assess_preference_promotion(target_objects: list[dict[str, Any]]) -> PromotionDecision:
    """Return whether a set of objects should be promoted into a PreferenceNote.

    Requires convergent evidence from at least
    :data:`PREFERENCE_PROMOTION_MIN_EPISODES` distinct episodes — a higher bar
    than SchemaNote promotion.
    """
    if len(target_objects) < 2:
        return PromotionDecision(
            promote=False,
            reason="preference promotion requires at least two source objects",
            supporting_episode_ids=(),
            evidence_refs=tuple(obj["id"] for obj in target_objects),
            stability_score=0.0,
        )

    if any(obj["status"] != "active" for obj in target_objects):
        return PromotionDecision(
            promote=False,
            reason="preference promotion candidates must all be active",
            supporting_episode_ids=(),
            evidence_refs=tuple(obj["id"] for obj in target_objects),
            stability_score=0.0,
        )

    episode_ids = sorted(
        {
            str(obj.get("metadata", {}).get("episode_id"))
            for obj in target_objects
            if obj.get("metadata", {}).get("episode_id")
        }
    )
    if len(episode_ids) < PREFERENCE_PROMOTION_MIN_EPISODES:
        return PromotionDecision(
            promote=False,
            reason=(
                f"preference promotion requires at least {PREFERENCE_PROMOTION_MIN_EPISODES} "
                f"distinct episodes; found {len(episode_ids)}"
            ),
            supporting_episode_ids=tuple(episode_ids),
            evidence_refs=tuple(obj["id"] for obj in target_objects),
            stability_score=0.0,
        )

    stability_score = round(
        min(0.90, 0.50 + 0.08 * len(target_objects) + 0.05 * len(episode_ids)),
        4,
    )
    return PromotionDecision(
        promote=True,
        reason=(
            "preference convergence from "
            f"{len(target_objects)} objects across {len(episode_ids)} episodes"
        ),
        supporting_episode_ids=tuple(episode_ids),
        evidence_refs=tuple(obj["id"] for obj in target_objects),
        stability_score=stability_score,
    )
