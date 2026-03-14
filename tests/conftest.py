from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from mind.kernel.store import SQLiteMemoryStore
from mind.offline_jobs import (
    OfflineJob,
    OfflineJobKind,
    OfflineJobStatus,
)


@pytest.fixture(autouse=True)
def _enable_test_only_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIND_ALLOW_SQLITE_FOR_TESTS", "1")


# ---------------------------------------------------------------------------
# Shared store factory
# ---------------------------------------------------------------------------


@pytest.fixture()
def make_store(tmp_path: Path) -> Callable[..., SQLiteMemoryStore]:
    """Return a factory that creates isolated ``SQLiteMemoryStore`` instances.

    Each call returns a *new* store backed by its own SQLite file so tests
    that need multiple stores can simply call the factory twice.

    Usage::

        def test_something(make_store):
            with make_store() as store:
                ...
    """
    _counter = 0

    def _factory(name: str | None = None) -> SQLiteMemoryStore:
        nonlocal _counter
        _counter += 1
        fname = f"{name or 'store'}.sqlite3" if name else f"store_{_counter}.sqlite3"
        return SQLiteMemoryStore(tmp_path / fname)

    return _factory


# ---------------------------------------------------------------------------
# Shared FakeOfflineJobStore — stub tier (no-op claim/complete/fail/cancel)
# ---------------------------------------------------------------------------


class FakeJobStoreStub:
    """Minimal ``OfflineJobStore`` stub: records enqueued jobs, returns them
    via ``iter_offline_jobs``.  Claim always returns ``None``; lifecycle
    methods are no-ops.  Suitable for tests that only need to inspect which
    jobs were enqueued.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, OfflineJob] = {}

    def enqueue_offline_job(self, job: OfflineJob | dict[str, Any]) -> None:
        validated = OfflineJob.model_validate(job)
        self._jobs[validated.job_id] = validated

    def iter_offline_jobs(
        self,
        *,
        statuses: Iterable[OfflineJobStatus] = (),
    ) -> list[OfflineJob]:
        jobs = list(self._jobs.values())
        allowed = set(statuses)
        if allowed:
            jobs = [j for j in jobs if j.status in allowed]
        return sorted(jobs, key=lambda j: (j.created_at, j.job_id))

    def claim_offline_job(
        self,
        *,
        worker_id: str,
        now: datetime,
        job_kinds: Iterable[OfflineJobKind] = (),
    ) -> OfflineJob | None:
        return None

    def complete_offline_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        completed_at: datetime,
        result: dict[str, Any],
    ) -> None:
        pass

    def fail_offline_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        failed_at: datetime,
        error: dict[str, Any],
    ) -> None:
        pass

    def cancel_offline_job(
        self,
        job_id: str,
        *,
        cancelled_at: datetime,
        error: dict[str, Any],
    ) -> None:
        pass


# ---------------------------------------------------------------------------
# Shared FakeOfflineJobStore — full-fidelity tier (real lifecycle)
# ---------------------------------------------------------------------------


class FakeJobStoreFull:
    """In-memory ``OfflineJobStore`` with full job lifecycle: claim picks the
    highest-priority pending job, and complete/fail/cancel update status.
    Initialise with a list of pre-seeded jobs for worker tests.
    """

    def __init__(self, jobs: list[OfflineJob] | None = None) -> None:
        self._jobs: dict[str, OfflineJob] = (
            {job.job_id: job for job in jobs} if jobs else {}
        )

    def enqueue_offline_job(self, job: OfflineJob | dict[str, Any]) -> None:
        validated = OfflineJob.model_validate(job)
        self._jobs[validated.job_id] = validated

    def iter_offline_jobs(
        self,
        *,
        statuses: Iterable[OfflineJobStatus] = (),
    ) -> list[OfflineJob]:
        jobs = list(self._jobs.values())
        allowed = set(statuses)
        if allowed:
            jobs = [job for job in jobs if job.status in allowed]
        return sorted(jobs, key=lambda job: (job.created_at, job.job_id))

    def claim_offline_job(
        self,
        *,
        worker_id: str,
        now: datetime,
        job_kinds: Iterable[OfflineJobKind] = (),
    ) -> OfflineJob | None:
        allowed_job_kinds = set(job_kinds)
        candidates = [
            job
            for job in self._jobs.values()
            if job.status is OfflineJobStatus.PENDING
            and job.available_at <= now
            and job.attempt_count < job.max_attempts
            and (not allowed_job_kinds or job.job_kind in allowed_job_kinds)
        ]
        if not candidates:
            return None
        selected = max(
            candidates,
            key=lambda job: (job.priority, -job.created_at.timestamp()),
        )
        claimed = selected.model_copy(
            update={
                "status": OfflineJobStatus.RUNNING,
                "attempt_count": selected.attempt_count + 1,
                "locked_by": worker_id,
                "locked_at": now,
                "updated_at": now,
            },
        )
        self._jobs[claimed.job_id] = claimed
        return claimed

    def complete_offline_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        completed_at: datetime,
        result: dict[str, Any],
    ) -> None:
        job = self._jobs[job_id]
        self._jobs[job_id] = job.model_copy(
            update={
                "status": OfflineJobStatus.SUCCEEDED,
                "completed_at": completed_at,
                "updated_at": completed_at,
                "result": result,
                "error": None,
            },
        )

    def fail_offline_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        failed_at: datetime,
        error: dict[str, Any],
    ) -> None:
        job = self._jobs[job_id]
        self._jobs[job_id] = job.model_copy(
            update={
                "status": OfflineJobStatus.FAILED,
                "completed_at": failed_at,
                "updated_at": failed_at,
                "result": None,
                "error": error,
            },
        )

    def cancel_offline_job(
        self,
        job_id: str,
        *,
        cancelled_at: datetime,
        error: dict[str, Any],
    ) -> None:
        job = self._jobs[job_id]
        self._jobs[job_id] = job.model_copy(
            update={
                "status": OfflineJobStatus.FAILED,
                "completed_at": cancelled_at,
                "updated_at": cancelled_at,
                "result": None,
                "error": error,
            },
        )
