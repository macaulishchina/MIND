"""Backward-compatible re-export for offline job contracts."""

from mind.offline_jobs import (
    OfflineJob,
    OfflineJobKind,
    OfflineJobStatus,
    OfflineJobStore,
    PromoteSchemaJobPayload,
    ReflectEpisodeJobPayload,
    RefreshEmbeddingsJobPayload,
    ResolveConflictJobPayload,
    UpdatePriorityJobPayload,
    VerifyProposalJobPayload,
    new_offline_job,
    utc_now,
)

__all__ = [
    "OfflineJob",
    "OfflineJobKind",
    "OfflineJobStatus",
    "OfflineJobStore",
    "PromoteSchemaJobPayload",
    "ReflectEpisodeJobPayload",
    "RefreshEmbeddingsJobPayload",
    "ResolveConflictJobPayload",
    "UpdatePriorityJobPayload",
    "VerifyProposalJobPayload",
    "new_offline_job",
    "utc_now",
]
