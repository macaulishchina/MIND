"""Offline maintenance job contracts."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class OfflineJobKind(StrEnum):
    """Supported offline maintenance job kinds."""

    REFLECT_EPISODE = "reflect_episode"
    PROMOTE_SCHEMA = "promote_schema"


class OfflineJobStatus(StrEnum):
    """Lifecycle states for offline jobs."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ReflectEpisodeJobPayload(BaseModel):
    """Payload for reflect_episode jobs."""

    episode_id: str = Field(min_length=1)
    focus: str = Field(min_length=1, default="offline replay reflection")


class PromoteSchemaJobPayload(BaseModel):
    """Payload for synthesize-schema promotion jobs."""

    target_refs: list[str] = Field(min_length=2)
    reason: str = Field(min_length=1)


class OfflineJob(BaseModel):
    """Persisted offline job row."""

    model_config = ConfigDict(use_enum_values=False)

    job_id: str = Field(min_length=1)
    job_kind: OfflineJobKind
    status: OfflineJobStatus = OfflineJobStatus.PENDING
    payload: dict[str, Any]
    priority: float = Field(default=0.5, ge=0, le=1)
    available_at: datetime
    created_at: datetime
    updated_at: datetime
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)
    locked_by: str | None = None
    locked_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class OfflineJobStore(Protocol):
    """Minimal queue interface used by the offline worker."""

    def enqueue_offline_job(self, job: OfflineJob | dict[str, Any]) -> None: ...

    def iter_offline_jobs(
        self,
        *,
        statuses: Iterable[OfflineJobStatus] = (),
    ) -> list[OfflineJob]: ...

    def claim_offline_job(
        self,
        *,
        worker_id: str,
        now: datetime,
        job_kinds: Iterable[OfflineJobKind] = (),
    ) -> OfflineJob | None: ...

    def complete_offline_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        completed_at: datetime,
        result: dict[str, Any],
    ) -> None: ...

    def fail_offline_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        failed_at: datetime,
        error: dict[str, Any],
    ) -> None: ...


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def new_offline_job(
    *,
    job_kind: OfflineJobKind,
    payload: BaseModel | dict[str, Any],
    priority: float = 0.5,
    available_at: datetime | None = None,
    max_attempts: int = 3,
    now: datetime | None = None,
    job_id: str | None = None,
) -> OfflineJob:
    """Create a validated offline job payload with consistent timestamps."""

    created_at = now or utc_now()
    ready_at = available_at or created_at
    payload_json = (
        payload.model_dump(mode="json") if isinstance(payload, BaseModel) else dict(payload)
    )
    return OfflineJob(
        job_id=job_id or f"offline-job-{uuid4().hex}",
        job_kind=job_kind,
        payload=payload_json,
        priority=priority,
        available_at=ready_at,
        created_at=created_at,
        updated_at=created_at,
        max_attempts=max_attempts,
    )
