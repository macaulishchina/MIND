"""Backward-compatible re-export for offline job contracts."""

from __future__ import annotations

from mind.offline_jobs import (
    AutoArchiveJobPayload,
    DiscoverLinksJobPayload,
    OfflineJob,
    OfflineJobKind,
    OfflineJobStatus,
    OfflineJobStore,
    PromotePolicyJobPayload,
    PromotePreferenceJobPayload,
    PromoteSchemaJobPayload,
    RebuildArtifactIndexJobPayload,
    ReflectEpisodeJobPayload,
    RefreshEmbeddingsJobPayload,
    ResolveConflictJobPayload,
    UpdatePriorityJobPayload,
    VerifyProposalJobPayload,
    new_offline_job,
    utc_now,
)

__all__ = [
    "AutoArchiveJobPayload",
    "DiscoverLinksJobPayload",
    "OfflineJob",
    "OfflineJobKind",
    "OfflineJobStatus",
    "OfflineJobStore",
    "PromotePolicyJobPayload",
    "PromotePreferenceJobPayload",
    "PromoteSchemaJobPayload",
    "RebuildArtifactIndexJobPayload",
    "ReflectEpisodeJobPayload",
    "RefreshEmbeddingsJobPayload",
    "ResolveConflictJobPayload",
    "UpdatePriorityJobPayload",
    "VerifyProposalJobPayload",
    "new_offline_job",
    "utc_now",
]
