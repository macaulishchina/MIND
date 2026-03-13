"""Dynamic priority computation (Phase α-2).

Provides :func:`compute_effective_priority` which blends a base priority
with recency, feedback, and type-bonus signals.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Weight factors for the blended priority formula.
W_BASE = 0.4
W_RECENCY = 0.2
W_FEEDBACK = 0.3
W_TYPE_BONUS = 0.1

# Type bonus lookup (same scale as the old _replay_score type bonuses).
_TYPE_BONUS: dict[str, float] = {
    "ReflectionNote": 0.70,
    "SummaryNote": 0.45,
    "SchemaNote": 0.40,
    "TaskEpisode": 0.10,
    "RawRecord": -0.05,
}

# Normalise type bonus to 0-1 range for the formula.
_MAX_TYPE_BONUS = max(_TYPE_BONUS.values())
_MIN_TYPE_BONUS = min(_TYPE_BONUS.values())
_BONUS_RANGE = max(_MAX_TYPE_BONUS - _MIN_TYPE_BONUS, 1e-9)


def compute_effective_priority(
    obj: dict[str, Any],
    *,
    now: datetime | None = None,
) -> float:
    """Return the effective priority for *obj*.

    Formula::

        base_priority * 0.4
      + recency_score * 0.2
      + feedback_score * 0.3
      + type_bonus * 0.1

    Where:
    - ``feedback_score = (positive - negative) / max(positive + negative, 1)``
      mapped to 0-1 range.
    - ``recency_score = 1.0 / (1 + days_since_last_access / 30)``
    - ``type_bonus`` is a normalised bonus per object type.

    All sub-signals are clamped to [0, 1] before combining so the result
    stays in a sane range.
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)

    metadata = obj.get("metadata", {})

    # Base priority (already 0-1 by convention).
    base_priority = _clamp(float(obj.get("priority", 0.5)))

    # Recency score.
    last_accessed = metadata.get("last_accessed_at")
    if last_accessed:
        try:
            last_dt = datetime.fromisoformat(str(last_accessed))
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            days_since = max((now - last_dt).total_seconds() / 86400.0, 0.0)
        except (ValueError, TypeError):
            days_since = 30.0
    else:
        days_since = 30.0  # treat never-accessed as moderately stale
    recency_score = _clamp(1.0 / (1.0 + days_since / 30.0))

    # Feedback score.
    positive = max(int(metadata.get("feedback_positive_count", 0)), 0)
    negative = max(int(metadata.get("feedback_negative_count", 0)), 0)
    total = positive + negative
    raw_feedback = (positive - negative) / max(total, 1)  # range [-1, 1]
    feedback_score = _clamp((raw_feedback + 1.0) / 2.0)  # map to [0, 1]

    # Type bonus.
    object_type = str(obj.get("type", ""))
    raw_bonus = _TYPE_BONUS.get(object_type, 0.0)
    type_bonus = _clamp((raw_bonus - _MIN_TYPE_BONUS) / _BONUS_RANGE)

    effective = (
        W_BASE * base_priority
        + W_RECENCY * recency_score
        + W_FEEDBACK * feedback_score
        + W_TYPE_BONUS * type_bonus
    )
    return round(effective, 4)


def effective_priority_or_base(obj: dict[str, Any]) -> float:
    """Return metadata ``effective_priority`` if present, else ``obj['priority']``."""
    ep = obj.get("metadata", {}).get("effective_priority")
    if ep is not None:
        try:
            return float(ep)
        except (ValueError, TypeError):
            pass
    return float(obj.get("priority", 0.5))


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))
