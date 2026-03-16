"""Tests for Phase α-2: Priority Signal Evolution.

Covers:
- compute_effective_priority formula correctness
- Feedback positive/negative influence on effective priority
- Time-decay recency signal
- effective_priority_or_base fallback
- UPDATE_PRIORITY offline job kind exists
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mind.kernel.priority import (
    compute_effective_priority,
    effective_priority_or_base,
)
from mind.offline_jobs import OfflineJobKind

FIXED_NOW = datetime(2026, 3, 14, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _obj(
    *,
    obj_type: str = "SummaryNote",
    priority: float = 0.5,
    feedback_positive: int = 0,
    feedback_negative: int = 0,
    last_accessed_at: str | None = None,
    effective_priority: float | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "summary_scope": "session",
        "input_refs": [],
        "compression_ratio_estimate": 0.5,
        "feedback_positive_count": feedback_positive,
        "feedback_negative_count": feedback_negative,
    }
    if last_accessed_at is not None:
        metadata["last_accessed_at"] = last_accessed_at
    if effective_priority is not None:
        metadata["effective_priority"] = effective_priority
    return {
        "id": "obj-test",
        "type": obj_type,
        "priority": priority,
        "metadata": metadata,
    }


# ---------------------------------------------------------------------------
# Priority formula tests
# ---------------------------------------------------------------------------


class TestComputeEffectivePriority:
    def test_default_object_returns_reasonable_value(self) -> None:
        obj = _obj()
        ep = compute_effective_priority(obj, now=FIXED_NOW)
        assert 0.0 <= ep <= 1.0

    def test_positive_feedback_increases_priority(self) -> None:
        base = _obj(feedback_positive=0)
        boosted = _obj(feedback_positive=10)
        ep_base = compute_effective_priority(base, now=FIXED_NOW)
        ep_boosted = compute_effective_priority(boosted, now=FIXED_NOW)
        assert ep_boosted > ep_base

    def test_negative_feedback_decreases_priority(self) -> None:
        base = _obj(feedback_negative=0)
        penalized = _obj(feedback_negative=10)
        ep_base = compute_effective_priority(base, now=FIXED_NOW)
        ep_penalized = compute_effective_priority(penalized, now=FIXED_NOW)
        assert ep_penalized < ep_base

    def test_recent_access_increases_priority(self) -> None:
        stale = _obj()  # no last_accessed_at → treated as 30 days stale
        recent = _obj(last_accessed_at=FIXED_NOW.isoformat())
        ep_stale = compute_effective_priority(stale, now=FIXED_NOW)
        ep_recent = compute_effective_priority(recent, now=FIXED_NOW)
        assert ep_recent > ep_stale

    def test_high_base_priority_raises_effective(self) -> None:
        low = _obj(priority=0.1)
        high = _obj(priority=0.9)
        ep_low = compute_effective_priority(low, now=FIXED_NOW)
        ep_high = compute_effective_priority(high, now=FIXED_NOW)
        assert ep_high > ep_low

    def test_type_bonus_differs_by_type(self) -> None:
        reflection = _obj(obj_type="ReflectionNote")
        raw = _obj(obj_type="RawRecord")
        ep_reflection = compute_effective_priority(reflection, now=FIXED_NOW)
        ep_raw = compute_effective_priority(raw, now=FIXED_NOW)
        assert ep_reflection > ep_raw, "ReflectionNote should have higher type bonus than RawRecord"

    def test_result_clamped_to_valid_range(self) -> None:
        obj = _obj(priority=1.0, feedback_positive=100)
        ep = compute_effective_priority(obj, now=FIXED_NOW)
        assert 0.0 <= ep <= 1.0


class TestEffectivePriorityOrBase:
    def test_returns_metadata_effective_priority_when_present(self) -> None:
        obj = _obj(effective_priority=0.85)
        assert effective_priority_or_base(obj) == 0.85

    def test_falls_back_to_base_priority(self) -> None:
        obj = _obj(priority=0.6)
        assert effective_priority_or_base(obj) == 0.6

    def test_falls_back_on_invalid_effective_priority(self) -> None:
        obj = _obj(priority=0.4)
        obj["metadata"]["effective_priority"] = "not-a-number"
        assert effective_priority_or_base(obj) == 0.4


class TestUpdatePriorityJobKind:
    def test_update_priority_in_offline_job_kinds(self) -> None:
        assert hasattr(OfflineJobKind, "UPDATE_PRIORITY")
        assert OfflineJobKind.UPDATE_PRIORITY == "update_priority"
