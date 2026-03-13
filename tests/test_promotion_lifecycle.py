"""Tests for Phase β-4: Promotion Pipeline + Proposal Lifecycle
(test_promotion_lifecycle.py).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from mind.kernel.schema import VALID_PROPOSAL_STATUS, validate_object
from mind.kernel.retrieval import matches_retrieval_filters
from mind.kernel.store import SQLiteMemoryStore
from mind.offline import OfflineJobKind, new_offline_job
from mind.offline.scheduler import OfflineJobScheduler
from mind.offline.service import OfflineMaintenanceService
from mind.offline_jobs import OfflineJob, VerifyProposalJobPayload

FIXED_TIMESTAMP = datetime(2026, 3, 13, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts() -> str:
    return FIXED_TIMESTAMP.isoformat()


def _schema_note(
    object_id: str = "schema-001",
    *,
    proposal_status: str | None = None,
    episode_refs: list[str] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "kind": "semantic",
        "evidence_refs": episode_refs or ["ref-001", "ref-002"],
        "stability_score": 0.75,
        "promotion_source_refs": ["ref-001"],
    }
    if proposal_status is not None:
        meta["proposal_status"] = proposal_status
    return {
        "id": object_id,
        "type": "SchemaNote",
        "content": {"rule": "test rule"},
        "source_refs": ["ref-001"],
        "created_at": _ts(),
        "updated_at": _ts(),
        "version": 1,
        "status": "active",
        "priority": 0.65,
        "metadata": meta,
    }


def _raw_object(
    object_id: str,
    *,
    episode_id: str = "ep-001",
) -> dict[str, Any]:
    return {
        "id": object_id,
        "type": "RawRecord",
        "content": {"text": f"content for {object_id}"},
        "source_refs": [],
        "created_at": _ts(),
        "updated_at": _ts(),
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": {
            "record_kind": "user_message",
            "episode_id": episode_id,
            "timestamp_order": 1,
        },
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
# β-4: SchemaNote proposal_status schema validation
# ---------------------------------------------------------------------------


def test_schema_note_validates_without_proposal_status() -> None:
    """β-4: SchemaNote without proposal_status is still valid (backward compat)."""
    obj = _schema_note()
    errors = validate_object(obj)
    assert errors == []


def test_schema_note_validates_with_proposed_status() -> None:
    """β-4: SchemaNote with proposal_status=proposed validates."""
    obj = _schema_note(proposal_status="proposed")
    errors = validate_object(obj)
    assert errors == []


def test_schema_note_validates_with_committed_status() -> None:
    """β-4: SchemaNote with proposal_status=committed validates."""
    obj = _schema_note(proposal_status="committed")
    errors = validate_object(obj)
    assert errors == []


def test_schema_note_validates_with_verified_status() -> None:
    """β-4: SchemaNote with proposal_status=verified validates."""
    obj = _schema_note(proposal_status="verified")
    errors = validate_object(obj)
    assert errors == []


def test_schema_note_validates_with_rejected_status() -> None:
    """β-4: SchemaNote with proposal_status=rejected validates."""
    obj = _schema_note(proposal_status="rejected")
    errors = validate_object(obj)
    assert errors == []


def test_schema_note_rejects_invalid_proposal_status() -> None:
    """β-4: SchemaNote with unknown proposal_status fails validation."""
    obj = _schema_note(proposal_status="pending_review")
    errors = validate_object(obj)
    assert any("proposal_status" in e for e in errors)


def test_valid_proposal_status_set() -> None:
    """β-4: VALID_PROPOSAL_STATUS contains the expected values."""
    assert VALID_PROPOSAL_STATUS == {"proposed", "verified", "committed", "rejected"}


# ---------------------------------------------------------------------------
# β-4: Retrieval filter excludes proposed/rejected SchemaNotes
# ---------------------------------------------------------------------------


def test_proposed_schema_note_excluded_from_retrieval() -> None:
    """β-4: SchemaNote with proposal_status=proposed is excluded by default retrieval."""
    obj = _schema_note(proposal_status="proposed")
    result = matches_retrieval_filters(
        obj,
        object_types=[],
        statuses=[],
        episode_id=None,
        task_id=None,
    )
    assert result is False


def test_rejected_schema_note_excluded_from_retrieval() -> None:
    """β-4: SchemaNote with proposal_status=rejected is excluded by default retrieval."""
    obj = _schema_note(proposal_status="rejected")
    result = matches_retrieval_filters(
        obj,
        object_types=[],
        statuses=[],
        episode_id=None,
        task_id=None,
    )
    assert result is False


def test_committed_schema_note_included_in_retrieval() -> None:
    """β-4: SchemaNote with proposal_status=committed participates in retrieval."""
    obj = _schema_note(proposal_status="committed")
    result = matches_retrieval_filters(
        obj,
        object_types=[],
        statuses=[],
        episode_id=None,
        task_id=None,
    )
    assert result is True


def test_schema_note_without_proposal_status_included_in_retrieval() -> None:
    """β-4: SchemaNote without proposal_status is treated as committed (backward compat)."""
    obj = _schema_note()  # no proposal_status
    result = matches_retrieval_filters(
        obj,
        object_types=[],
        statuses=[],
        episode_id=None,
        task_id=None,
    )
    assert result is True


def test_raw_record_not_affected_by_proposal_filter() -> None:
    """β-4: Non-SchemaNote objects are not filtered by proposal_status logic."""
    obj = _raw_object("raw-001")
    result = matches_retrieval_filters(
        obj,
        object_types=[],
        statuses=[],
        episode_id=None,
        task_id=None,
    )
    assert result is True


# ---------------------------------------------------------------------------
# β-4: Scheduler hooks
# ---------------------------------------------------------------------------


def test_scheduler_on_schema_promoted_enqueues_verify_proposal() -> None:
    """β-4: on_schema_promoted enqueues VERIFY_PROPOSAL job."""
    job_store = _FakeJobStore()
    scheduler = OfflineJobScheduler(job_store, clock=lambda: FIXED_TIMESTAMP)
    job_id = scheduler.on_schema_promoted("schema-001")
    assert job_id is not None
    jobs = job_store.iter_offline_jobs()
    assert len(jobs) == 1
    assert jobs[0].job_kind is OfflineJobKind.VERIFY_PROPOSAL
    assert jobs[0].payload["schema_note_id"] == "schema-001"


# ---------------------------------------------------------------------------
# β-4: VerifyProposalJobPayload
# ---------------------------------------------------------------------------


def test_verify_proposal_payload_validates() -> None:
    """β-4: VerifyProposalJobPayload validates successfully."""
    payload = VerifyProposalJobPayload(schema_note_id="schema-001")
    assert payload.schema_note_id == "schema-001"


def test_verify_proposal_job_kind_exists() -> None:
    """β-4: VERIFY_PROPOSAL is a valid OfflineJobKind."""
    assert OfflineJobKind.VERIFY_PROPOSAL == "verify_proposal"


# ---------------------------------------------------------------------------
# β-4: OfflineMaintenanceService processes VERIFY_PROPOSAL
# ---------------------------------------------------------------------------


def test_offline_service_verify_proposal_commits_cross_episode_schema(
    tmp_path: Path,
) -> None:
    """β-4: VERIFY_PROPOSAL commits a SchemaNote with cross-episode evidence."""
    with SQLiteMemoryStore(tmp_path / "test.sqlite3") as store:
        # Write evidence objects from two different episodes.
        ref1 = _raw_object("ref-001", episode_id="ep-001")
        ref2 = _raw_object("ref-002", episode_id="ep-002")
        store.insert_object(ref1)
        store.insert_object(ref2)

        schema = _schema_note(
            "schema-001",
            proposal_status="proposed",
            episode_refs=["ref-001", "ref-002"],
        )
        store.insert_object(schema)

        service = OfflineMaintenanceService(store)
        job = new_offline_job(
            job_kind=OfflineJobKind.VERIFY_PROPOSAL,
            payload=VerifyProposalJobPayload(schema_note_id="schema-001"),
            now=FIXED_TIMESTAMP,
        )
        result = service.process_job(job, actor="test-actor")
        assert result["verified"] is True
        assert result["proposal_status"] == "committed"

        # Confirm the store has the updated object.
        updated = store.read_object("schema-001")
        assert updated["metadata"].get("proposal_status") == "committed"


def test_offline_service_verify_proposal_rejects_single_episode_schema(
    tmp_path: Path,
) -> None:
    """β-4: VERIFY_PROPOSAL rejects a SchemaNote with only one episode's evidence."""
    with SQLiteMemoryStore(tmp_path / "test.sqlite3") as store:
        ref1 = _raw_object("ref-001", episode_id="ep-001")
        ref2 = _raw_object("ref-002", episode_id="ep-001")  # same episode!
        store.insert_object(ref1)
        store.insert_object(ref2)

        schema = _schema_note(
            "schema-002",
            proposal_status="proposed",
            episode_refs=["ref-001", "ref-002"],
        )
        store.insert_object(schema)

        service = OfflineMaintenanceService(store)
        job = new_offline_job(
            job_kind=OfflineJobKind.VERIFY_PROPOSAL,
            payload=VerifyProposalJobPayload(schema_note_id="schema-002"),
            now=FIXED_TIMESTAMP,
        )
        result = service.process_job(job, actor="test-actor")
        assert result["verified"] is False
        assert result["proposal_status"] == "rejected"

        updated = store.read_object("schema-002")
        assert updated["metadata"].get("proposal_status") == "rejected"


def test_rejected_schema_not_in_retrieval(tmp_path: Path) -> None:
    """β-4: After rejection, SchemaNote no longer appears in retrieval results."""
    with SQLiteMemoryStore(tmp_path / "test.sqlite3") as store:
        ref1 = _raw_object("ref-001", episode_id="ep-001")
        store.insert_object(ref1)

        schema = _schema_note(
            "schema-003",
            proposal_status="rejected",
            episode_refs=["ref-001"],
        )
        store.insert_object(schema)

        # Search for SchemaNote objects.
        all_objects = list(store.iter_latest_objects())
        schema_in_results = any(
            obj["id"] == "schema-003"
            for obj in all_objects
            if matches_retrieval_filters(
                obj,
                object_types=["SchemaNote"],
                statuses=[],
                episode_id=None,
                task_id=None,
            )
        )
    assert schema_in_results is False
