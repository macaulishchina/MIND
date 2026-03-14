"""Tests for Phase β-3: Workspace Evidence Diversity (test_workspace_diversity.py)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mind.workspace.policy import (
    FLASH_POLICY,
    RECALL_POLICY,
    RECONSTRUCT_POLICY,
    SlotAllocationPolicy,
    apply_diversity_policy,
    evidence_diversity_score,
)

FIXED_TIMESTAMP = datetime(2026, 3, 13, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts() -> str:
    return FIXED_TIMESTAMP.isoformat()


def _obj(
    object_id: str,
    *,
    object_type: str = "RawRecord",
    episode_id: str = "ep-001",
    score: float = 0.5,
    conflict_candidates: list | None = None,
) -> tuple[dict[str, Any], float]:
    meta: dict[str, Any] = {
        "record_kind": "user_message",
        "episode_id": episode_id,
        "timestamp_order": 1,
    }
    if conflict_candidates is not None:
        meta["conflict_candidates"] = conflict_candidates
    if object_type != "RawRecord":
        meta.pop("record_kind", None)
        meta.pop("timestamp_order", None)
    obj = {
        "id": object_id,
        "type": object_type,
        "content": {"text": f"content for {object_id}"},
        "source_refs": [f"src-{object_id}"],
        "created_at": _ts(),
        "updated_at": _ts(),
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": meta,
    }
    return obj, score


# ---------------------------------------------------------------------------
# β-3: SlotAllocationPolicy
# ---------------------------------------------------------------------------


def test_slot_allocation_policy_defaults() -> None:
    """β-3: SlotAllocationPolicy has sensible defaults."""
    policy = SlotAllocationPolicy()
    assert policy.min_raw_evidence_slots == 1
    assert policy.min_diverse_episode_slots == 1
    assert policy.include_conflict_evidence is True


def test_flash_policy_is_permissive() -> None:
    """β-3: FLASH_POLICY has no diversity requirements."""
    assert FLASH_POLICY.min_raw_evidence_slots == 0
    assert FLASH_POLICY.min_diverse_episode_slots == 0
    assert FLASH_POLICY.include_conflict_evidence is False


def test_reconstruct_policy_is_strict() -> None:
    """β-3: RECONSTRUCT_POLICY enforces multi-episode diversity."""
    assert RECONSTRUCT_POLICY.min_diverse_episode_slots >= 2


# ---------------------------------------------------------------------------
# β-3: apply_diversity_policy
# ---------------------------------------------------------------------------


def test_apply_diversity_policy_returns_up_to_slot_limit() -> None:
    """β-3: apply_diversity_policy returns at most slot_limit items."""
    candidates = [_obj(f"obj-{i:03d}", score=float(i)) for i in range(10)]
    selected = apply_diversity_policy(
        list(reversed(candidates)),  # highest score first
        slot_limit=4,
        policy=RECALL_POLICY,
    )
    assert len(selected) <= 4


def test_apply_diversity_policy_all_same_episode_promotes_diverse() -> None:
    """β-3: When all candidates are from the same episode, diverse ones get promoted."""
    # 4 objects from ep-001, 1 from ep-002 (lower score)
    candidates = [_obj(f"obj-{i:03d}", episode_id="ep-001", score=float(10 - i)) for i in range(4)]
    candidates.append(_obj("obj-ep2", episode_id="ep-002", score=0.1))
    # Sort by score descending
    candidates.sort(key=lambda x: x[1], reverse=True)
    policy = RECALL_POLICY
    selected = apply_diversity_policy(candidates, slot_limit=4, policy=policy)
    episodes_in_selected = {obj.get("metadata", {}).get("episode_id") for obj, _ in selected}
    # With diversity policy, ep-002 should be included.
    assert "ep-002" in episodes_in_selected


def test_apply_diversity_policy_no_policy_is_greedy() -> None:
    """β-3: Passing FLASH_POLICY (no diversity) just takes top N by score."""
    candidates = [_obj(f"obj-{i:03d}", episode_id="ep-001", score=float(10 - i)) for i in range(6)]
    candidates.sort(key=lambda x: x[1], reverse=True)
    selected = apply_diversity_policy(candidates, slot_limit=3, policy=FLASH_POLICY)
    # Greedy: top 3 by score, all from ep-001
    assert len(selected) == 3
    for obj, _ in selected:
        assert obj["metadata"]["episode_id"] == "ep-001"


def test_apply_diversity_policy_promotes_conflict_evidence() -> None:
    """β-3: Objects with conflict_candidates are promoted into workspace."""
    # Three regular objects + one with conflict evidence (lower score)
    candidates = [
        _obj("regular-1", episode_id="ep-001", score=0.9),
        _obj("regular-2", episode_id="ep-001", score=0.8),
        _obj("regular-3", episode_id="ep-002", score=0.7),
        _obj(
            "conflict-obj",
            episode_id="ep-003",
            score=0.1,
            conflict_candidates=[{"relation": "contradict"}],
        ),
    ]
    candidates.sort(key=lambda x: x[1], reverse=True)
    policy = RECALL_POLICY
    selected = apply_diversity_policy(candidates, slot_limit=3, policy=policy)
    selected_ids = {obj["id"] for obj, _ in selected}
    # With conflict_evidence policy, the conflict object should be included.
    assert "conflict-obj" in selected_ids


def test_apply_diversity_policy_empty_candidates() -> None:
    """β-3: apply_diversity_policy handles empty candidate list gracefully."""
    result = apply_diversity_policy([], slot_limit=4, policy=RECALL_POLICY)
    assert result == []


def test_apply_diversity_policy_slot_limit_zero() -> None:
    """β-3: apply_diversity_policy with slot_limit=0 returns empty list."""
    candidates = [_obj("obj-001", score=1.0)]
    result = apply_diversity_policy(candidates, slot_limit=0, policy=RECALL_POLICY)
    assert result == []


def test_apply_diversity_policy_graceful_degradation() -> None:
    """β-3: apply_diversity_policy degrades gracefully when constraints can't be met."""
    # Only 2 candidates, both from same episode - can't satisfy min_diverse_episode_slots=2
    candidates = [
        _obj("obj-001", episode_id="ep-001", score=0.9),
        _obj("obj-002", episode_id="ep-001", score=0.8),
    ]
    policy = RECONSTRUCT_POLICY  # requires 2 diverse episodes
    # Should not raise, just return best effort
    result = apply_diversity_policy(candidates, slot_limit=2, policy=policy)
    assert len(result) <= 2


# ---------------------------------------------------------------------------
# β-3: evidence_diversity_score
# ---------------------------------------------------------------------------


def test_evidence_diversity_score_single_object() -> None:
    """β-3: Diversity score for a single object is 0.0."""
    obj, _ = _obj("obj-001")
    assert evidence_diversity_score([obj]) == 0.0


def test_evidence_diversity_score_multi_episode() -> None:
    """β-3: Higher diversity with objects from different episodes."""
    objs_single = [_obj(f"obj-{i}", episode_id="ep-001")[0] for i in range(4)]
    objs_multi = [_obj(f"obj-{i}", episode_id=f"ep-{i:03d}")[0] for i in range(4)]
    score_single = evidence_diversity_score(objs_single)
    score_multi = evidence_diversity_score(objs_multi)
    assert score_multi >= score_single


def test_evidence_diversity_score_mixed_types() -> None:
    """β-3: Mixed object types increase the diversity score."""
    obj_single_type = [
        _obj(f"obj-{i}", object_type="RawRecord", episode_id=f"ep-{i}")[0] for i in range(4)
    ]
    obj_mixed_type = [
        _obj("obj-a", object_type="RawRecord", episode_id="ep-0")[0],
        _obj("obj-b", object_type="SummaryNote", episode_id="ep-1")[0],
        _obj("obj-c", object_type="ReflectionNote", episode_id="ep-2")[0],
        _obj("obj-d", object_type="EntityNode", episode_id="ep-3")[0],
    ]
    score_single = evidence_diversity_score(obj_single_type)
    score_mixed = evidence_diversity_score(obj_mixed_type)
    assert score_mixed >= score_single


def test_evidence_diversity_score_range() -> None:
    """β-3: Diversity score is always in [0, 1]."""
    for n in [2, 4, 8]:
        objs = [_obj(f"obj-{i}", episode_id=f"ep-{i}")[0] for i in range(n)]
        score = evidence_diversity_score(objs)
        assert 0.0 <= score <= 1.0
