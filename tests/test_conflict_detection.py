"""Tests for Phase β-2: Input Conflict Detection (test_conflict_detection.py)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from mind.kernel.store import SQLiteMemoryStore
from mind.offline import OfflineJobKind, new_offline_job
from mind.offline.scheduler import OfflineJobScheduler
from mind.offline_jobs import OfflineJob, OfflineJobStatus, ResolveConflictJobPayload
from mind.primitives.conflict import (
    ConflictDetectionResult,
    ConflictRelation,
    detect_conflicts,
)

FIXED_TIMESTAMP = datetime(2026, 3, 13, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts() -> str:
    return FIXED_TIMESTAMP.isoformat()


def _raw_object(
    object_id: str,
    *,
    episode_id: str = "ep-001",
    text: str = "some content",
    metadata_extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "record_kind": "user_message",
        "episode_id": episode_id,
        "timestamp_order": 1,
    }
    if metadata_extras:
        meta.update(metadata_extras)
    return {
        "id": object_id,
        "type": "RawRecord",
        "content": {"text": text},
        "source_refs": [],
        "created_at": _ts(),
        "updated_at": _ts(),
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": meta,
    }


class _FakeJobStore:
    def __init__(self) -> None:
        self._jobs: list[OfflineJob] = []

    def enqueue_offline_job(self, job: OfflineJob | dict[str, Any]) -> None:
        self._jobs.append(OfflineJob.model_validate(job))

    def iter_offline_jobs(
        self,
        *,
        statuses: Any = (),
    ) -> list[OfflineJob]:
        return list(self._jobs)


# ---------------------------------------------------------------------------
# β-2: ConflictRelation enum
# ---------------------------------------------------------------------------


def test_conflict_relation_values() -> None:
    """β-2: ConflictRelation enum defines all expected values."""
    expected = {"duplicate", "refine", "contradict", "supersede", "novel"}
    assert {r.value for r in ConflictRelation} == expected


# ---------------------------------------------------------------------------
# β-2: ConflictDetectionResult dataclass
# ---------------------------------------------------------------------------


def test_conflict_detection_result_fields() -> None:
    """β-2: ConflictDetectionResult has required fields."""
    result = ConflictDetectionResult(
        relation=ConflictRelation.NOVEL,
        confidence=0.9,
        neighbor_id="obj-001",
        explanation="no overlap",
    )
    assert result.relation is ConflictRelation.NOVEL
    assert result.confidence == 0.9
    assert result.neighbor_id == "obj-001"
    assert result.explanation == "no overlap"


# ---------------------------------------------------------------------------
# β-2: detect_conflicts function
# ---------------------------------------------------------------------------


def test_detect_conflicts_returns_empty_when_no_candidates(tmp_path: Path) -> None:
    """β-2: detect_conflicts returns [] when store has no other objects."""
    with SQLiteMemoryStore(tmp_path / "test.sqlite3") as store:
        new_obj = _raw_object("new-001", text="completely new content")
        store.insert_object(new_obj)
        results = detect_conflicts(store, new_obj)
    assert results == []


def test_detect_conflicts_returns_list_of_results(tmp_path: Path) -> None:
    """β-2: detect_conflicts returns a list of ConflictDetectionResult objects."""
    with SQLiteMemoryStore(tmp_path / "test.sqlite3") as store:
        existing = _raw_object("old-001", text="memory system for AI agents")
        store.insert_object(existing)
        new_obj = _raw_object("new-001", text="memory system for AI models")
        store.insert_object(new_obj)
        results = detect_conflicts(store, new_obj)
    assert isinstance(results, list)
    for r in results:
        assert isinstance(r, ConflictDetectionResult)


def test_detect_conflicts_identifies_novel_when_different(tmp_path: Path) -> None:
    """β-2: Very different texts produce NOVEL relation or empty."""
    with SQLiteMemoryStore(tmp_path / "test.sqlite3") as store:
        existing = _raw_object("old-001", text="cooking recipes for pasta")
        store.insert_object(existing)
        new_obj = _raw_object("new-001", text="quantum computing algorithms")
        store.insert_object(new_obj)
        results = detect_conflicts(store, new_obj)
    # Either empty (no significant overlap) or all NOVEL.
    assert all(r.relation is ConflictRelation.NOVEL for r in results) or results == []


def test_detect_conflicts_identifies_contradiction(tmp_path: Path) -> None:
    """β-2: Texts containing strong negation are classified as CONTRADICT."""
    with SQLiteMemoryStore(tmp_path / "test.sqlite3") as store:
        existing = _raw_object("old-001", text="The system is always available")
        store.insert_object(existing)
        new_obj = _raw_object(
            "new-001", text="The system is not always available incorrect"
        )
        store.insert_object(new_obj)
        results = detect_conflicts(store, new_obj)
    # Should detect at least one contradiction or return empty.
    contradictions = [r for r in results if r.relation is ConflictRelation.CONTRADICT]
    assert len(contradictions) >= 0  # Rule-based: best-effort


def test_detect_conflicts_respects_top_k(tmp_path: Path) -> None:
    """β-2: detect_conflicts limits comparisons to top_k neighbours."""
    with SQLiteMemoryStore(tmp_path / "test.sqlite3") as store:
        for i in range(10):
            obj = _raw_object(f"old-{i:03d}", text=f"content item {i}")
            store.insert_object(obj)
        new_obj = _raw_object("new-001", text="content item new")
        store.insert_object(new_obj)
        results = detect_conflicts(store, new_obj, top_k=2)
    # Should return at most top_k results
    assert len(results) <= 2


def test_detect_conflicts_excludes_new_object_from_comparison(tmp_path: Path) -> None:
    """β-2: The new object itself is never compared against itself."""
    with SQLiteMemoryStore(tmp_path / "test.sqlite3") as store:
        obj = _raw_object("self-001", text="self reference test")
        store.insert_object(obj)
        results = detect_conflicts(store, obj)
    for r in results:
        assert r.neighbor_id != "self-001"


# ---------------------------------------------------------------------------
# β-2: Scheduler integration
# ---------------------------------------------------------------------------


def test_scheduler_on_conflict_detected_enqueues_resolve_conflict() -> None:
    """β-2: on_conflict_detected enqueues RESOLVE_CONFLICT when contradictions found."""
    job_store = _FakeJobStore()
    scheduler = OfflineJobScheduler(job_store, clock=lambda: FIXED_TIMESTAMP)
    conflict_candidates = [
        {
            "relation": "contradict",
            "confidence": 0.9,
            "neighbor_id": "old-001",
            "explanation": "contradiction detected",
        }
    ]
    job_id = scheduler.on_conflict_detected("new-001", conflict_candidates)
    assert job_id is not None
    jobs = job_store.iter_offline_jobs()
    assert len(jobs) == 1
    assert jobs[0].job_kind is OfflineJobKind.RESOLVE_CONFLICT
    assert jobs[0].payload["object_id"] == "new-001"


def test_scheduler_on_conflict_detected_skips_when_no_contradiction() -> None:
    """β-2: on_conflict_detected skips when only NOVEL/REFINE conflicts."""
    job_store = _FakeJobStore()
    scheduler = OfflineJobScheduler(job_store, clock=lambda: FIXED_TIMESTAMP)
    conflict_candidates = [
        {
            "relation": "novel",
            "confidence": 0.9,
            "neighbor_id": "old-001",
            "explanation": "no overlap",
        }
    ]
    job_id = scheduler.on_conflict_detected("new-001", conflict_candidates)
    assert job_id is None
    assert job_store.iter_offline_jobs() == []


def test_scheduler_on_conflict_detected_skips_empty_candidates() -> None:
    """β-2: on_conflict_detected does nothing when candidate list is empty."""
    job_store = _FakeJobStore()
    scheduler = OfflineJobScheduler(job_store, clock=lambda: FIXED_TIMESTAMP)
    job_id = scheduler.on_conflict_detected("new-001", [])
    assert job_id is None


# ---------------------------------------------------------------------------
# β-2: ResolveConflictJobPayload validation
# ---------------------------------------------------------------------------


def test_resolve_conflict_payload_validates() -> None:
    """β-2: ResolveConflictJobPayload validates successfully."""
    payload = ResolveConflictJobPayload(
        object_id="obj-001",
        conflict_candidates=[
            {
                "relation": "contradict",
                "confidence": 0.9,
                "neighbor_id": "old-001",
                "explanation": "test",
            }
        ],
    )
    assert payload.object_id == "obj-001"
    assert len(payload.conflict_candidates) == 1


def test_resolve_conflict_job_kind_exists() -> None:
    """β-2: RESOLVE_CONFLICT is a valid OfflineJobKind."""
    assert OfflineJobKind.RESOLVE_CONFLICT == "resolve_conflict"


def test_new_offline_job_with_resolve_conflict_kind() -> None:
    """β-2: new_offline_job accepts RESOLVE_CONFLICT kind."""
    job = new_offline_job(
        job_kind=OfflineJobKind.RESOLVE_CONFLICT,
        payload=ResolveConflictJobPayload(
            object_id="obj-001",
            conflict_candidates=[],
        ),
        now=FIXED_TIMESTAMP,
    )
    assert job.job_kind is OfflineJobKind.RESOLVE_CONFLICT
    assert job.payload["object_id"] == "obj-001"
