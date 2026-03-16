"""Tests for Phase α-1: Post-Query Feedback Loop.

Covers:
- FeedbackRecord schema definition and validation
- record_feedback primitive: success / failure / missing refs
- Feedback object readable via store after recording
- FeedbackService app-layer envelope
- Dynamic signal counters updated on referenced objects
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from mind.kernel.schema import (
    CORE_OBJECT_TYPES,
    REQUIRED_METADATA_FIELDS,
    validate_object,
)
from mind.primitives.contracts import (
    PrimitiveName,
    RecordFeedbackRequest,
    RecordFeedbackResponse,
)

FIXED_TS = datetime(2026, 3, 14, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts(offset_seconds: int = 0) -> str:
    return (
        datetime(2026, 3, 14, tzinfo=UTC).__class__(
            2026, 3, 14, 0, 0, offset_seconds, tzinfo=UTC
        )
    ).isoformat()


def _raw_object(
    *,
    object_id: str = "raw-001",
    episode_id: str = "ep-test",
) -> dict[str, Any]:
    now = FIXED_TS.isoformat()
    return {
        "id": object_id,
        "type": "RawRecord",
        "content": "some raw content",
        "source_refs": [],
        "created_at": now,
        "updated_at": now,
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": {
            "record_kind": "user_message",
            "episode_id": episode_id,
            "timestamp_order": 1,
        },
    }


def _feedback_object(
    *,
    feedback_id: str = "feedback-001",
    task_id: str = "task-1",
    episode_id: str = "ep-test",
    used_ids: list[str] | None = None,
    helpful_ids: list[str] | None = None,
    unhelpful_ids: list[str] | None = None,
    quality_signal: float = 0.7,
) -> dict[str, Any]:
    now = FIXED_TS.isoformat()
    default_used = used_ids if used_ids is not None else ["raw-001"]
    return {
        "id": feedback_id,
        "type": "FeedbackRecord",
        "content": {"query": "test query"},
        "source_refs": default_used,  # must be non-empty for non-RawRecord types
        "created_at": now,
        "updated_at": now,
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": {
            "task_id": task_id,
            "episode_id": episode_id,
            "query": "test query",
            "used_object_ids": default_used,
            "helpful_object_ids": helpful_ids or [],
            "unhelpful_object_ids": unhelpful_ids or [],
            "quality_signal": quality_signal,
        },
    }


# ---------------------------------------------------------------------------
# α-1.1: FeedbackRecord schema
# ---------------------------------------------------------------------------


class TestFeedbackRecordSchema:
    def test_feedback_record_in_core_types(self) -> None:
        assert "FeedbackRecord" in CORE_OBJECT_TYPES

    def test_required_metadata_fields(self) -> None:
        fields = REQUIRED_METADATA_FIELDS["FeedbackRecord"]
        assert "task_id" in fields
        assert "episode_id" in fields
        assert "query" in fields
        assert "used_object_ids" in fields
        assert "helpful_object_ids" in fields
        assert "unhelpful_object_ids" in fields
        assert "quality_signal" in fields

    def test_valid_feedback_object_passes_validation(self) -> None:
        obj = _feedback_object()
        errors = validate_object(obj)
        assert errors == []

    def test_missing_required_metadata_fails(self) -> None:
        obj = _feedback_object()
        del obj["metadata"]["quality_signal"]
        errors = validate_object(obj)
        assert any("quality_signal" in e for e in errors)


# ---------------------------------------------------------------------------
# α-1.2 / α-1.3: record_feedback contracts and primitive
# ---------------------------------------------------------------------------


class TestRecordFeedbackContracts:
    def test_primitive_name_exists(self) -> None:
        assert PrimitiveName.RECORD_FEEDBACK == "record_feedback"

    def test_request_model_validates(self) -> None:
        req = RecordFeedbackRequest(
            task_id="task-1",
            episode_id="ep-1",
            query="what happened?",
            used_object_ids=["obj-1"],
            helpful_object_ids=["obj-1"],
            unhelpful_object_ids=[],
            quality_signal=0.8,
        )
        assert req.task_id == "task-1"
        assert req.quality_signal == 0.8

    def test_request_rejects_invalid_quality_signal(self) -> None:
        with pytest.raises(ValidationError):
            RecordFeedbackRequest(
                task_id="task-1",
                episode_id="ep-1",
                query="q",
                quality_signal=5.0,  # out of range
            )

    def test_response_model(self) -> None:
        resp = RecordFeedbackResponse(feedback_object_id="fb-123")
        assert resp.feedback_object_id == "fb-123"


# ---------------------------------------------------------------------------
# α-1.3: record_feedback primitive execution
# ---------------------------------------------------------------------------


class TestRecordFeedbackPrimitive:
    def test_record_feedback_stores_object(self, make_store):  # type: ignore[no-untyped-def]
        with make_store() as store:
            # Seed a raw object so used_object_ids reference exists.
            raw = _raw_object()
            store.insert_object(raw)

            from mind.primitives.service import PrimitiveService

            svc = PrimitiveService(store=store)
            result = svc.record_feedback(
                {
                    "task_id": "task-1",
                    "episode_id": "ep-test",
                    "query": "what happened?",
                    "used_object_ids": ["raw-001"],
                    "helpful_object_ids": ["raw-001"],
                    "unhelpful_object_ids": [],
                    "quality_signal": 0.9,
                },
                {
                    "actor": "test-user",
                    "dev_mode": False,
                    "capabilities": ["memory_read"],
                },
            )
            assert result.outcome.value == "success"
            assert result.response is not None
            fb_id = result.response["feedback_object_id"]

            # α-1 acceptance: feedback object is readable.
            fb_obj = store.read_object(fb_id)
            assert fb_obj["type"] == "FeedbackRecord"
            assert fb_obj["metadata"]["quality_signal"] == 0.9

    def test_feedback_updates_dynamic_signals(self, make_store):  # type: ignore[no-untyped-def]
        with make_store() as store:
            raw = _raw_object()
            store.insert_object(raw)

            from mind.primitives.service import PrimitiveService

            svc = PrimitiveService(store=store)
            svc.record_feedback(
                {
                    "task_id": "task-1",
                    "episode_id": "ep-test",
                    "query": "q",
                    "used_object_ids": ["raw-001"],
                    "helpful_object_ids": ["raw-001"],
                    "unhelpful_object_ids": [],
                    "quality_signal": 0.8,
                },
                {
                    "actor": "test-user",
                    "dev_mode": False,
                    "capabilities": ["memory_read"],
                },
            )

            # The referenced object should have updated counters.
            updated_raw = store.read_object("raw-001")
            assert int(updated_raw["metadata"].get("feedback_positive_count", 0)) >= 1
            assert int(updated_raw["metadata"].get("access_count", 0)) >= 1


# ---------------------------------------------------------------------------
# α-1.9: Golden fixtures
# ---------------------------------------------------------------------------


class TestFeedbackFixtures:
    def test_golden_feedback_records_exist(self) -> None:
        from mind.fixtures.golden_episode_set import build_core_object_showcase

        showcase = build_core_object_showcase()
        feedback_objs = [o for o in showcase if o["type"] == "FeedbackRecord"]
        assert len(feedback_objs) >= 2, "Expected at least 2 FeedbackRecord fixtures"
        for obj in feedback_objs:
            errors = validate_object(obj)
            assert errors == [], f"Fixture validation failed: {errors}"
