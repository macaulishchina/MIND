"""Offline job application service."""

from __future__ import annotations

from mind.app._service_utils import new_response
from mind.app.contracts import AppError, AppErrorCode, AppRequest, AppResponse, AppStatus
from mind.app.errors import map_domain_error
from mind.kernel.store import MemoryStore
from mind.offline.service import OfflineMaintenanceService
from mind.offline_jobs import (
    OfflineJobKind,
    OfflineJobStatus,
    new_offline_job,
    utc_now,
)


class OfflineJobAppService:
    """Manage offline maintenance jobs.

    Methods: ``submit_job``, ``get_job``, ``list_jobs``, ``cancel_job``.
    """

    def __init__(
        self,
        store: MemoryStore,
        offline_service: OfflineMaintenanceService,
    ) -> None:
        self._store = store
        self._offline = offline_service

    def submit_job(self, req: AppRequest) -> AppResponse:
        """Submit a new offline job."""
        resp = new_response(req)

        try:
            job_kind_str = req.input.get("job_kind", "")
            try:
                job_kind = OfflineJobKind(job_kind_str)
            except ValueError:
                resp.status = AppStatus.ERROR
                resp.error = AppError(
                    code=AppErrorCode.VALIDATION_ERROR,
                    message=f"unsupported job kind: {job_kind_str}",
                )
                return resp

            payload = req.input.get("payload", {})
            priority = req.input.get("priority", 0.5)

            job = new_offline_job(
                job_kind=job_kind,
                payload=payload,
                priority=priority,
            )

            store = self._store
            if hasattr(store, "enqueue_offline_job"):
                store.enqueue_offline_job(job)
            else:
                resp.status = AppStatus.ERROR
                resp.error = AppError(
                    code=AppErrorCode.UNSUPPORTED_OPERATION,
                    message="current store does not support offline jobs",
                )
                return resp

            resp.status = AppStatus.OK
            resp.result = {
                "job_id": job.job_id,
                "status": job.status.value,
            }
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.error = map_domain_error(exc)

        return resp

    def get_job(self, req: AppRequest) -> AppResponse:
        """Get a job by ID."""
        resp = new_response(req)

        try:
            job_id = req.input.get("job_id", "")
            if not job_id:
                resp.status = AppStatus.ERROR
                resp.error = AppError(
                    code=AppErrorCode.VALIDATION_ERROR, message="job_id required"
                )
                return resp

            store = self._store
            if not hasattr(store, "iter_offline_jobs"):
                resp.status = AppStatus.ERROR
                resp.error = AppError(
                    code=AppErrorCode.UNSUPPORTED_OPERATION,
                    message="current store does not support offline jobs",
                )
                return resp

            jobs = list(store.iter_offline_jobs())
            found = [j for j in jobs if j.job_id == job_id]
            if not found:
                resp.status = AppStatus.NOT_FOUND
                resp.error = AppError(
                    code=AppErrorCode.NOT_FOUND, message=f"job {job_id} not found"
                )
                return resp

            resp.status = AppStatus.OK
            resp.result = found[0].model_dump(mode="json")
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.error = map_domain_error(exc)

        return resp

    def list_jobs(self, req: AppRequest) -> AppResponse:
        """List offline jobs with optional status filter."""
        resp = new_response(req)

        try:
            store = self._store
            if not hasattr(store, "iter_offline_jobs"):
                resp.status = AppStatus.ERROR
                resp.error = AppError(
                    code=AppErrorCode.UNSUPPORTED_OPERATION,
                    message="current store does not support offline jobs",
                )
                return resp

            status_filter = req.input.get("statuses", [])
            statuses = [OfflineJobStatus(s) for s in status_filter] if status_filter else []

            jobs = list(store.iter_offline_jobs(statuses=statuses))
            limit = req.input.get("limit", 50)
            offset = req.input.get("offset", 0)
            sliced = jobs[offset : offset + limit]

            resp.status = AppStatus.OK
            resp.result = {
                "jobs": [j.model_dump(mode="json") for j in sliced],
                "total": len(jobs),
            }
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.error = map_domain_error(exc)

        return resp

    def cancel_job(self, req: AppRequest) -> AppResponse:
        """Cancel a pending job (mark as failed with cancel reason)."""
        resp = new_response(req)

        try:
            job_id = req.input.get("job_id", "")
            if not job_id:
                resp.status = AppStatus.ERROR
                resp.error = AppError(
                    code=AppErrorCode.VALIDATION_ERROR, message="job_id required"
                )
                return resp

            store = self._store
            if hasattr(store, "cancel_offline_job"):
                store.cancel_offline_job(
                    job_id,
                    cancelled_at=utc_now(),
                    error={"reason": "cancelled by user"},
                )
            elif hasattr(store, "fail_offline_job"):
                store.fail_offline_job(
                    job_id,
                    worker_id="cancel",
                    failed_at=utc_now(),
                    error={"reason": "cancelled by user"},
                )
            else:
                resp.status = AppStatus.ERROR
                resp.error = AppError(
                    code=AppErrorCode.UNSUPPORTED_OPERATION,
                    message="current store does not support offline jobs",
                )
                return resp

            resp.status = AppStatus.OK
            resp.result = {"job_id": job_id, "cancelled": True}
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.error = map_domain_error(exc)

        return resp
