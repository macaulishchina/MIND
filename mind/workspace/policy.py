"""Slot allocation policy for workspace evidence diversity (Phase β-3).

Defines :class:`SlotAllocationPolicy` and the diversity-rebalancing algorithm
used by :class:`~mind.workspace.builder.WorkspaceBuilder`.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SlotAllocationPolicy:
    """Constraints that guide workspace slot selection.

    All constraints are *soft*: when not enough candidates are available the
    builder applies best-effort satisfaction and degrades gracefully.

    Attributes:
        min_raw_evidence_slots: Minimum number of ``RawRecord`` objects that
            must appear in the final workspace (default 1).
        min_diverse_episode_slots: Minimum number of slots that come from
            *different* episodes relative to the first selected slot's episode
            (default 1).
        include_conflict_evidence: When ``True``, objects whose metadata
            contains ``conflict_candidates`` are preferentially promoted into
            the workspace.
    """

    min_raw_evidence_slots: int = 1
    min_diverse_episode_slots: int = 1
    include_conflict_evidence: bool = True


# Pre-built policies for each access mode.
FLASH_POLICY = SlotAllocationPolicy(
    min_raw_evidence_slots=0,
    min_diverse_episode_slots=0,
    include_conflict_evidence=False,
)

RECALL_POLICY = SlotAllocationPolicy(
    min_raw_evidence_slots=1,
    min_diverse_episode_slots=1,
    include_conflict_evidence=True,
)

RECONSTRUCT_POLICY = SlotAllocationPolicy(
    min_raw_evidence_slots=1,
    min_diverse_episode_slots=2,
    include_conflict_evidence=True,
)

REFLECTIVE_POLICY = SlotAllocationPolicy(
    min_raw_evidence_slots=1,
    min_diverse_episode_slots=2,
    include_conflict_evidence=True,
)


def apply_diversity_policy(
    ranked_candidates: list[tuple[dict[str, Any], float]],
    *,
    slot_limit: int,
    policy: SlotAllocationPolicy,
) -> list[tuple[dict[str, Any], float]]:
    """Select *slot_limit* candidates that best satisfy *policy* constraints.

    Algorithm:
    1. Greedily fill slots by descending score.
    2. Check which policy constraints are not yet satisfied.
    3. For each unmet constraint, replace the *lowest-priority* slot already
       selected with the best remaining candidate that satisfies the constraint.
    4. Never replace a slot with a lower-scoring candidate unless required.

    Args:
        ranked_candidates: Pre-sorted ``(object, score)`` pairs in descending
            order.  Callers are responsible for sorting.
        slot_limit: Maximum number of slots to fill.
        policy: The :class:`SlotAllocationPolicy` to enforce.

    Returns:
        A list of ``(object, score)`` pairs of length ``<= slot_limit``.
    """
    if not ranked_candidates:
        return []
    if slot_limit <= 0:
        return []

    # Step 1: greedy fill.
    selected = list(ranked_candidates[:slot_limit])
    remaining = list(ranked_candidates[slot_limit:])

    # Step 2: check constraints.
    selected = _enforce_raw_evidence(selected, remaining, policy)
    selected = _enforce_episode_diversity(selected, remaining, policy)
    selected = _enforce_conflict_evidence(selected, remaining, policy)

    return selected[:slot_limit]


def evidence_diversity_score(selected: list[dict[str, Any]]) -> float:
    """Compute a diversity score in ``[0, 1]`` for a set of selected objects.

    The score combines:
    * Shannon entropy of ``object_type`` distribution (normalised by log N).
    * Episode diversity ratio (unique episodes / total selected).

    Returns ``0.0`` when fewer than two objects are provided.
    """
    if len(selected) < 2:
        return 0.0

    # Object type entropy.
    type_counts = Counter(obj["type"] for obj in selected)
    n = len(selected)
    type_entropy = 0.0
    for count in type_counts.values():
        p = count / n
        type_entropy -= p * math.log(p)
    max_entropy = math.log(n)
    normalized_entropy = type_entropy / max_entropy if max_entropy > 0 else 0.0

    # Episode diversity.
    episodes = {
        obj.get("metadata", {}).get("episode_id")
        for obj in selected
        if obj.get("metadata", {}).get("episode_id")
    }
    episode_ratio = len(episodes) / n if n > 0 else 0.0

    return round((normalized_entropy + episode_ratio) / 2.0, 4)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _episode_id(obj: dict[str, Any]) -> str | None:
    return obj.get("metadata", {}).get("episode_id")


def _has_conflict_candidates(obj: dict[str, Any]) -> bool:
    return bool(obj.get("metadata", {}).get("conflict_candidates"))


def _enforce_raw_evidence(
    selected: list[tuple[dict[str, Any], float]],
    remaining: list[tuple[dict[str, Any], float]],
    policy: SlotAllocationPolicy,
) -> list[tuple[dict[str, Any], float]]:
    if policy.min_raw_evidence_slots <= 0:
        return selected

    raw_count = sum(1 for obj, _ in selected if obj["type"] == "RawRecord")
    if raw_count >= policy.min_raw_evidence_slots:
        return selected

    needed = policy.min_raw_evidence_slots - raw_count
    for candidate, score in remaining:
        if needed <= 0:
            break
        if candidate["type"] != "RawRecord":
            continue
        selected = _swap_lowest(selected, (candidate, score))
        needed -= 1

    return selected


def _enforce_episode_diversity(
    selected: list[tuple[dict[str, Any], float]],
    remaining: list[tuple[dict[str, Any], float]],
    policy: SlotAllocationPolicy,
) -> list[tuple[dict[str, Any], float]]:
    if policy.min_diverse_episode_slots <= 0:
        return selected

    if not selected:
        return selected

    # Determine the dominant episode (most common non-None episode_id).
    episode_ids = [_episode_id(obj) for obj, _ in selected]
    non_none = [e for e in episode_ids if e is not None]
    if not non_none:
        return selected

    episode_counts = Counter(non_none)
    dominant = episode_counts.most_common(1)[0][0]

    # Count how many selected objects differ from dominant episode.
    diverse_count = sum(
        1 for obj, _ in selected if _episode_id(obj) is not None and _episode_id(obj) != dominant
    )

    if diverse_count >= policy.min_diverse_episode_slots:
        return selected

    needed = policy.min_diverse_episode_slots - diverse_count
    for candidate, score in remaining:
        if needed <= 0:
            break
        cand_episode = _episode_id(candidate)
        if cand_episode is None or cand_episode == dominant:
            continue
        selected = _swap_lowest(selected, (candidate, score))
        needed -= 1

    return selected


def _enforce_conflict_evidence(
    selected: list[tuple[dict[str, Any], float]],
    remaining: list[tuple[dict[str, Any], float]],
    policy: SlotAllocationPolicy,
) -> list[tuple[dict[str, Any], float]]:
    """Promote conflict evidence objects into the workspace when available."""
    if not policy.include_conflict_evidence:
        return selected

    # Check whether any conflict evidence is already present.
    already_has_conflict = any(_has_conflict_candidates(obj) for obj, _ in selected)
    if already_has_conflict:
        return selected

    for candidate, score in remaining:
        if _has_conflict_candidates(candidate):
            selected = _swap_lowest(selected, (candidate, score))
            break

    return selected


def _swap_lowest(
    selected: list[tuple[dict[str, Any], float]],
    candidate: tuple[dict[str, Any], float],
) -> list[tuple[dict[str, Any], float]]:
    """Replace the lowest-scoring slot with *candidate* if the list is full.

    If *selected* is not at slot_limit (tracked externally), just append.
    This helper assumes the caller already checked slot budget.
    """
    if not selected:
        return [candidate]

    # Find the lowest-scoring entry.
    min_idx = min(range(len(selected)), key=lambda i: (selected[i][1], -i))
    result = list(selected)
    result[min_idx] = candidate
    return result
