"""Mode history cache for auto-mode decision enhancement (Phase β-5).

Maintains a ``task_family → Counter[AccessMode]`` mapping weighted by
:attr:`~mind.access.contracts.AccessRunResponse.answer_quality_signal` from
:class:`~mind.kernel.schema.FeedbackRecord` objects.

The cache is in-memory and intentionally not persisted — it is rebuilt from
FeedbackRecords on demand, or updated incrementally as new feedback arrives.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from mind.access.contracts import AccessMode, AccessTaskFamily


class ModeHistoryCache:
    """Tracks historical access-mode quality, keyed by task family.

    Callers record observations via :meth:`record` and retrieve the
    preferred mode via :meth:`preferred_mode`.

    Thread-safety: this class is **not** thread-safe.  Callers that share a
    single cache across threads should use external locking.
    """

    def __init__(self) -> None:
        # task_family → {mode → weighted_score}
        self._scores: dict[str, dict[str, float]] = {}

    # ------------------------------------------------------------------
    # Write API

    def record(
        self,
        mode: AccessMode,
        quality_signal: float,
        *,
        task_family: AccessTaskFamily | str | None = None,
    ) -> None:
        """Record one access run observation.

        Args:
            mode: The access mode that was used.
            quality_signal: Quality score in ``[-1, 1]``.  Positive values
                reinforce the mode; negative values penalise it.
            task_family: Optional task family key.  When ``None`` the
                observation is recorded under the ``"_all"`` bucket so it
                influences cross-family suggestions.
        """
        key = str(task_family) if task_family is not None else "_all"
        bucket = self._scores.setdefault(key, {})
        bucket[mode.value] = round(bucket.get(mode.value, 0.0) + float(quality_signal), 4)

    def record_from_feedback(self, feedback_object: dict[str, Any]) -> None:
        """Extract mode + quality signal from a FeedbackRecord and call :meth:`record`.

        The FeedbackRecord metadata is expected to contain:
        * ``access_mode``: the access mode string (optional).
        * ``quality_signal``: float in ``[-1, 1]``.
        * ``task_family``: optional task family string.
        """
        meta = feedback_object.get("metadata", {})
        quality = float(meta.get("quality_signal", 0.0))
        task_family = meta.get("task_family")
        mode_str = meta.get("access_mode")
        try:
            mode = AccessMode(mode_str) if mode_str else AccessMode.RECALL
        except ValueError:
            mode = AccessMode.RECALL
        try:
            family = AccessTaskFamily(task_family) if task_family else None
        except ValueError:
            family = None
        self.record(mode, quality, task_family=family)

    # ------------------------------------------------------------------
    # Read API

    def preferred_mode(
        self,
        task_family: AccessTaskFamily | str | None = None,
    ) -> AccessMode | None:
        """Return the mode with the highest accumulated quality score.

        Combines the ``task_family``-specific bucket (if present) with the
        ``"_all"`` cross-family bucket.

        Returns ``None`` when no history is available.
        """
        key = str(task_family) if task_family is not None else "_all"
        combined: dict[str, float] = {}

        for bucket_key in (key, "_all"):
            for mode_str, score in self._scores.get(bucket_key, {}).items():
                combined[mode_str] = combined.get(mode_str, 0.0) + score

        if not combined:
            return None
        best = max(combined, key=lambda m: combined[m])
        try:
            return AccessMode(best)
        except ValueError:
            return None

    def mode_counts(
        self,
        task_family: AccessTaskFamily | str | None = None,
    ) -> Counter[AccessMode]:
        """Return a :class:`~collections.Counter` of positive observations per mode.

        Only modes with a positive accumulated score are included.
        """
        key = str(task_family) if task_family is not None else "_all"
        result: Counter[AccessMode] = Counter()
        for mode_str, score in self._scores.get(key, {}).items():
            if score > 0:
                try:
                    result[AccessMode(mode_str)] += 1
                except ValueError:
                    pass
        return result

    def reset(self) -> None:
        """Clear all recorded history."""
        self._scores.clear()

    @classmethod
    def build_from_feedback_records(
        cls, feedback_objects: list[dict[str, Any]]
    ) -> ModeHistoryCache:
        """Rebuild a cache from a list of FeedbackRecord objects."""
        cache = cls()
        for obj in feedback_objects:
            if obj.get("type") == "FeedbackRecord":
                cache.record_from_feedback(obj)
        return cache
