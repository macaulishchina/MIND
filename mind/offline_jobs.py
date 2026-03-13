"""Stable offline maintenance job contracts shared outside ``mind.offline``."""

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
    UPDATE_PRIORITY = "update_priority"
    REFRESH_EMBEDDINGS = "refresh_embeddings"
    RESOLVE_CONFLICT = "resolve_conflict"
    VERIFY_PROPOSAL = "verify_proposal"
    PROMOTE_POLICY = "promote_policy"
    PROMOTE_PREFERENCE = "promote_preference"
    DISCOVER_LINKS = "discover_links"
    REBUILD_ARTIFACT_INDEX = "rebuild_artifact_index"
    AUTO_ARCHIVE = "auto_archive"


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


class UpdatePriorityJobPayload(BaseModel):
    """Payload for batch priority update jobs."""

    object_ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1, default="scheduled priority update")


class RefreshEmbeddingsJobPayload(BaseModel):
    """Payload for embedding refresh jobs (Phase β-1)."""

    object_ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1, default="refresh dense embeddings")


class ResolveConflictJobPayload(BaseModel):
    """Payload for conflict resolution jobs (Phase β-2)."""

    object_id: str = Field(min_length=1)
    conflict_candidates: list[dict[str, Any]] = Field(default_factory=list)


class VerifyProposalJobPayload(BaseModel):
    """Payload for proposal verification jobs (Phase β-4)."""

    schema_note_id: str = Field(min_length=1)


class PromotePolicyJobPayload(BaseModel):
    """Payload for policy promotion jobs (Phase γ-1)."""

    target_refs: list[str] = Field(min_length=2)
    reason: str = Field(min_length=1)


class PromotePreferenceJobPayload(BaseModel):
    """Payload for preference promotion jobs (Phase γ-1)."""

    target_refs: list[str] = Field(min_length=2)
    reason: str = Field(min_length=1)


class DiscoverLinksJobPayload(BaseModel):
    """Payload for automatic link discovery jobs (Phase γ-2)."""

    object_ids: list[str] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1)
    min_similarity: float = Field(default=0.7, ge=0.0, le=1.0)
    reason: str = Field(min_length=1, default="discover links via embedding similarity")


class RebuildArtifactIndexJobPayload(BaseModel):
    """Payload for artifact index rebuild jobs (Phase γ-4)."""

    object_ids: list[str] = Field(default_factory=list)
    min_content_length: int = Field(default=500, ge=1)
    reason: str = Field(min_length=1, default="rebuild artifact tree index")


class AutoArchiveJobPayload(BaseModel):
    """Payload for automatic archive jobs (Phase γ-5)."""

    dry_run: bool = False
    stale_days: int = Field(default=90, ge=1)
    reason: str = Field(min_length=1, default="auto-archive stale objects")


class OfflineJob(BaseModel):
    """Persisted offline job row."""

    model_config = ConfigDict(use_enum_values=False)

    job_id: str = Field(min_length=1)
    job_kind: OfflineJobKind
    status: OfflineJobStatus = OfflineJobStatus.PENDING
    payload: dict[str, Any]
    provider_selection: dict[str, Any] | None = None
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

    def cancel_offline_job(
        self,
        job_id: str,
        *,
        cancelled_at: datetime,
        error: dict[str, Any],
    ) -> None: ...


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def new_offline_job(
    *,
    job_kind: OfflineJobKind,
    payload: BaseModel | dict[str, Any],
    provider_selection: dict[str, Any] | None = None,
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
        provider_selection=(
            dict(provider_selection) if provider_selection is not None else None
        ),
        priority=priority,
        available_at=ready_at,
        created_at=created_at,
        updated_at=created_at,
        max_attempts=max_attempts,
    )
