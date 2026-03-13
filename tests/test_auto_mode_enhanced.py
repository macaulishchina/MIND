"""Tests for Phase β-5: Auto Mode Enhancement + β-S1: Evidence Summary
(test_auto_mode_enhanced.py).
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

import pytest

from mind.access.contracts import (
    AccessMode,
    AccessTaskFamily,
    EvidenceSummaryItem,
)
from mind.access.mode_history import ModeHistoryCache

FIXED_TIMESTAMP = datetime(2026, 3, 13, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# β-S1: EvidenceSummaryItem
# ---------------------------------------------------------------------------


def test_evidence_summary_item_validates() -> None:
    """β-S1: EvidenceSummaryItem validates successfully."""
    item = EvidenceSummaryItem(
        object_id="obj-001",
        object_type="RawRecord",
        brief="User said hello",
        relevance_score=0.85,
    )
    assert item.object_id == "obj-001"
    assert item.object_type == "RawRecord"
    assert item.brief == "User said hello"
    assert item.relevance_score == 0.85


def test_evidence_summary_item_relevance_score_bounds() -> None:
    """β-S1: EvidenceSummaryItem relevance_score must be in [0, 1]."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        EvidenceSummaryItem(
            object_id="obj-001",
            object_type="RawRecord",
            brief="brief",
            relevance_score=1.5,
        )

    with pytest.raises(ValidationError):
        EvidenceSummaryItem(
            object_id="obj-001",
            object_type="RawRecord",
            brief="brief",
            relevance_score=-0.1,
        )


def test_access_run_response_accepts_evidence_summary() -> None:
    """β-S1: AccessRunResponse accepts non-empty evidence_summary."""
    from mind.access.contracts import (
        AccessContextKind,
        AccessModeTraceEvent,
        AccessReasonCode,
        AccessRunResponse,
        AccessRunTrace,
        AccessSwitchKind,
        AccessTraceKind,
    )

    trace = AccessRunTrace(
        requested_mode=AccessMode.FLASH,
        resolved_mode=AccessMode.FLASH,
        events=[
            AccessModeTraceEvent(
                event_kind=AccessTraceKind.SELECT_MODE,
                mode=AccessMode.FLASH,
                summary="flash selected",
                reason_code=AccessReasonCode.EXPLICIT_MODE_REQUEST,
                switch_kind=AccessSwitchKind.INITIAL,
            ),
            AccessModeTraceEvent(
                event_kind=AccessTraceKind.MODE_SUMMARY,
                mode=AccessMode.FLASH,
                summary="flash complete",
            ),
        ],
    )
    item = EvidenceSummaryItem(
        object_id="obj-001",
        object_type="RawRecord",
        brief="User said hello",
        relevance_score=0.9,
    )
    response = AccessRunResponse(
        resolved_mode=AccessMode.FLASH,
        context_kind=AccessContextKind.RAW_TOPK,
        context_text="some context",
        context_token_count=10,
        trace=trace,
        evidence_summary=[item],
    )
    assert len(response.evidence_summary) == 1
    assert response.evidence_summary[0].object_id == "obj-001"


def test_access_run_response_evidence_summary_defaults_empty() -> None:
    """β-S1: AccessRunResponse evidence_summary defaults to empty list."""
    from mind.access.contracts import (
        AccessContextKind,
        AccessModeTraceEvent,
        AccessReasonCode,
        AccessRunResponse,
        AccessRunTrace,
        AccessSwitchKind,
        AccessTraceKind,
    )

    trace = AccessRunTrace(
        requested_mode=AccessMode.FLASH,
        resolved_mode=AccessMode.FLASH,
        events=[
            AccessModeTraceEvent(
                event_kind=AccessTraceKind.SELECT_MODE,
                mode=AccessMode.FLASH,
                summary="flash selected",
                reason_code=AccessReasonCode.EXPLICIT_MODE_REQUEST,
                switch_kind=AccessSwitchKind.INITIAL,
            ),
            AccessModeTraceEvent(
                event_kind=AccessTraceKind.MODE_SUMMARY,
                mode=AccessMode.FLASH,
                summary="flash complete",
            ),
        ],
    )
    response = AccessRunResponse(
        resolved_mode=AccessMode.FLASH,
        context_kind=AccessContextKind.RAW_TOPK,
        context_text="some context",
        context_token_count=10,
        trace=trace,
    )
    assert response.evidence_summary == []


# ---------------------------------------------------------------------------
# β-5: ModeHistoryCache
# ---------------------------------------------------------------------------


def test_mode_history_cache_starts_empty() -> None:
    """β-5: ModeHistoryCache starts with no history."""
    cache = ModeHistoryCache()
    assert cache.preferred_mode() is None


def test_mode_history_cache_record_positive() -> None:
    """β-5: Recording a positive signal makes that mode the preferred one."""
    cache = ModeHistoryCache()
    cache.record(AccessMode.RECALL, 1.0)
    cache.record(AccessMode.FLASH, -0.5)
    assert cache.preferred_mode() is AccessMode.RECALL


def test_mode_history_cache_record_accumulates() -> None:
    """β-5: Multiple observations for the same mode accumulate."""
    cache = ModeHistoryCache()
    cache.record(AccessMode.RECALL, 0.5)
    cache.record(AccessMode.RECALL, 0.5)
    cache.record(AccessMode.FLASH, 0.8)
    # Recall = 1.0, Flash = 0.8 → Recall wins
    assert cache.preferred_mode() is AccessMode.RECALL


def test_mode_history_cache_task_family_specific() -> None:
    """β-5: Preferences are tracked per task_family."""
    cache = ModeHistoryCache()
    cache.record(AccessMode.RECALL, 1.0, task_family=AccessTaskFamily.BALANCED)
    cache.record(AccessMode.FLASH, 1.0, task_family=AccessTaskFamily.SPEED_SENSITIVE)
    assert cache.preferred_mode(AccessTaskFamily.BALANCED) is AccessMode.RECALL
    assert cache.preferred_mode(AccessTaskFamily.SPEED_SENSITIVE) is AccessMode.FLASH


def test_mode_history_cache_all_bucket_fallback() -> None:
    """β-5: Cross-family (_all) observations influence all lookups."""
    cache = ModeHistoryCache()
    cache.record(AccessMode.RECONSTRUCT, 2.0)  # into _all bucket
    # Even for a specific family with no direct history, _all contributes.
    assert cache.preferred_mode(AccessTaskFamily.HIGH_CORRECTNESS) is AccessMode.RECONSTRUCT


def test_mode_history_cache_reset() -> None:
    """β-5: reset() clears all recorded history."""
    cache = ModeHistoryCache()
    cache.record(AccessMode.RECALL, 1.0)
    cache.reset()
    assert cache.preferred_mode() is None


def test_mode_history_cache_record_from_feedback() -> None:
    """β-5: record_from_feedback extracts mode and quality from FeedbackRecord."""
    cache = ModeHistoryCache()
    feedback_obj = {
        "type": "FeedbackRecord",
        "metadata": {
            "access_mode": "recall",
            "quality_signal": 0.8,
            "task_family": "balanced",
        },
    }
    cache.record_from_feedback(feedback_obj)
    assert cache.preferred_mode(AccessTaskFamily.BALANCED) is AccessMode.RECALL


def test_mode_history_cache_record_from_feedback_missing_mode() -> None:
    """β-5: record_from_feedback handles missing access_mode gracefully."""
    cache = ModeHistoryCache()
    feedback_obj = {
        "type": "FeedbackRecord",
        "metadata": {
            "quality_signal": 0.5,
        },
    }
    # Should not raise
    cache.record_from_feedback(feedback_obj)


def test_mode_history_cache_build_from_feedback_records() -> None:
    """β-5: build_from_feedback_records creates a populated cache."""
    feedback_objects = [
        {
            "type": "FeedbackRecord",
            "metadata": {
                "access_mode": "recall",
                "quality_signal": 1.0,
                "task_family": "balanced",
            },
        },
        {
            "type": "FeedbackRecord",
            "metadata": {
                "access_mode": "flash",
                "quality_signal": -0.5,
                "task_family": "balanced",
            },
        },
    ]
    cache = ModeHistoryCache.build_from_feedback_records(feedback_objects)
    # recall (1.0) vs flash (-0.5) → recall wins
    assert cache.preferred_mode(AccessTaskFamily.BALANCED) is AccessMode.RECALL


def test_mode_history_cache_build_from_feedback_ignores_non_feedback() -> None:
    """β-5: build_from_feedback_records ignores non-FeedbackRecord objects."""
    objects = [
        {
            "type": "RawRecord",
            "metadata": {"access_mode": "recall", "quality_signal": 1.0},
        }
    ]
    cache = ModeHistoryCache.build_from_feedback_records(objects)
    assert cache.preferred_mode() is None


def test_mode_history_cache_mode_counts() -> None:
    """β-5: mode_counts returns a Counter of positive observations per mode."""
    cache = ModeHistoryCache()
    cache.record(AccessMode.RECALL, 1.0)
    cache.record(AccessMode.RECALL, 0.5)
    cache.record(AccessMode.FLASH, -0.5)  # negative, should not appear
    counts = cache.mode_counts()
    assert AccessMode.RECALL in counts
    assert AccessMode.FLASH not in counts
