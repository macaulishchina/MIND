"""Single-process offline worker."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from .jobs import OfflineJobKind, OfflineJobStore
from .service import OfflineMaintenanceService


@dataclass(frozen=True)
class WorkerRunResult:
    """Aggregate outcome for a worker run."""

    claimed_jobs: int
    succeeded_jobs: int
    failed_jobs: int
    completed_job_ids: tuple[str, ...]


class OfflineWorker:
    """Claim and execute offline maintenance jobs."""

    def __init__(
        self,
        job_store: OfflineJobStore,
        maintenance_service: OfflineMaintenanceService,
        *,
        worker_id: str = "mind-offline-worker",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.job_store = job_store
        self.maintenance_service = maintenance_service
        self.worker_id = worker_id
        self._clock = clock or _utc_now

    def run_once(
        self,
        *,
        max_jobs: int = 1,
        job_kinds: Iterable[OfflineJobKind] = (),
    ) -> WorkerRunResult:
        """Claim and process up to `max_jobs` ready jobs."""

        completed_job_ids: list[str] = []
        succeeded_jobs = 0
        failed_jobs = 0

        for _ in range(max_jobs):
            now = self._clock()
            job = self.job_store.claim_offline_job(
                worker_id=self.worker_id,
                now=now,
                job_kinds=job_kinds,
            )
            if job is None:
                break

            try:
                result = self.maintenance_service.process_job(job, actor=self.worker_id)
            except Exception as exc:
                failed_jobs += 1
                self.job_store.fail_offline_job(
                    job.job_id,
                    worker_id=self.worker_id,
                    failed_at=self._clock(),
                    error={
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                )
                completed_job_ids.append(job.job_id)
                continue

            succeeded_jobs += 1
            self.job_store.complete_offline_job(
                job.job_id,
                worker_id=self.worker_id,
                completed_at=self._clock(),
                result=result,
            )
            completed_job_ids.append(job.job_id)

        return WorkerRunResult(
            claimed_jobs=len(completed_job_ids),
            succeeded_jobs=succeeded_jobs,
            failed_jobs=failed_jobs,
            completed_job_ids=tuple(completed_job_ids),
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)
