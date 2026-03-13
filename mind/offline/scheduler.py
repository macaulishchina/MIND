"""Auto-trigger scheduler for offline maintenance jobs (Phase α-3, β-2, β-4)."""

from __future__ import annotations

from typing import Any

from mind.offline_jobs import (
    OfflineJobKind,
    OfflineJobStore,
    ReflectEpisodeJobPayload,
    RefreshEmbeddingsJobPayload,
    ResolveConflictJobPayload,
    UpdatePriorityJobPayload,
    VerifyProposalJobPayload,
    new_offline_job,
    utc_now,
)

#: Minimum number of positive feedback hits on an object before a PROMOTE_SCHEMA
#: candidate job is auto-enqueued.
PROMOTE_SCHEMA_POSITIVE_FEEDBACK_THRESHOLD = 3


class OfflineJobScheduler:
    """Inspect memory events and auto-enqueue offline jobs.

    The scheduler is stateless and safe to call on every write path.  It only
    enqueues a job when a meaningful threshold is crossed; all decisions are
    deterministic given the input data.

    Usage example (inside a memory ingest service)::

        scheduler = OfflineJobScheduler(store)
        scheduler.on_episode_completed(episode_id="ep-abc", episode_object=episode_obj)
    """

    def __init__(
        self,
        job_store: OfflineJobStore,
        *,
        clock: Any = None,
        promote_threshold: int = PROMOTE_SCHEMA_POSITIVE_FEEDBACK_THRESHOLD,
    ) -> None:
        self._job_store = job_store
        self._clock: Any = clock or utc_now
        self._promote_threshold = promote_threshold

    # ------------------------------------------------------------------
    # Public hooks

    def on_episode_completed(
        self,
        episode_id: str,
        episode_object: dict[str, Any],
    ) -> str | None:
        """Auto-enqueue a REFLECT_EPISODE job when an episode result is set.

        Returns the new job_id if a job was enqueued, else ``None``.
        """
        result = episode_object.get("metadata", {}).get("result")
        if not result:
            return None
        focus = f"episode {episode_id} completed: {str(result)[:120]}"
        job = new_offline_job(
            job_kind=OfflineJobKind.REFLECT_EPISODE,
            payload=ReflectEpisodeJobPayload(episode_id=episode_id, focus=focus),
            priority=0.7,
            now=self._clock(),
        )
        self._job_store.enqueue_offline_job(job)
        return job.job_id

    def on_feedback_recorded(
        self,
        feedback_object: dict[str, Any],
        object_id: str,
        positive_feedback_count: int,
    ) -> str | None:
        """Auto-enqueue a PROMOTE_SCHEMA candidate job when positive feedback is high.

        Returns the new job_id if a job was enqueued, else ``None``.
        """
        if positive_feedback_count < self._promote_threshold:
            return None
        episode_id = feedback_object.get("metadata", {}).get("episode_id", "")
        reason = (
            f"object {object_id} received {positive_feedback_count} positive feedback hits"
        )
        job = new_offline_job(
            job_kind=OfflineJobKind.PROMOTE_SCHEMA,
            payload={"target_refs": [object_id, episode_id or object_id], "reason": reason},
            priority=0.6,
            now=self._clock(),
        )
        self._job_store.enqueue_offline_job(job)
        return job.job_id

    def schedule_priority_update(
        self,
        object_ids: list[str] | None = None,
        *,
        reason: str = "scheduled priority update",
        priority: float = 0.4,
    ) -> str:
        """Enqueue an UPDATE_PRIORITY job for the given objects (or all objects).

        Returns the new job_id.
        """
        job = new_offline_job(
            job_kind=OfflineJobKind.UPDATE_PRIORITY,
            payload=UpdatePriorityJobPayload(
                object_ids=object_ids or [],
                reason=reason,
            ),
            priority=priority,
            now=self._clock(),
        )
        self._job_store.enqueue_offline_job(job)
        return job.job_id

    def on_conflict_detected(
        self,
        object_id: str,
        conflict_candidates: list[dict[str, Any]],
    ) -> str | None:
        """Auto-enqueue a RESOLVE_CONFLICT job when contradictions are found (Phase β-2).

        Only enqueues when at least one candidate has relation == "contradict".

        Returns the new job_id if a job was enqueued, else ``None``.
        """
        has_contradiction = any(
            c.get("relation") == "contradict" for c in conflict_candidates
        )
        if not has_contradiction:
            return None
        job = new_offline_job(
            job_kind=OfflineJobKind.RESOLVE_CONFLICT,
            payload=ResolveConflictJobPayload(
                object_id=object_id,
                conflict_candidates=conflict_candidates,
            ),
            priority=0.7,
            now=self._clock(),
        )
        self._job_store.enqueue_offline_job(job)
        return job.job_id

    def on_schema_promoted(
        self,
        schema_note_id: str,
    ) -> str:
        """Auto-enqueue a VERIFY_PROPOSAL job after a SchemaNote is promoted (Phase β-4).

        Returns the new job_id.
        """
        job = new_offline_job(
            job_kind=OfflineJobKind.VERIFY_PROPOSAL,
            payload=VerifyProposalJobPayload(schema_note_id=schema_note_id),
            priority=0.65,
            now=self._clock(),
        )
        self._job_store.enqueue_offline_job(job)
        return job.job_id

    def schedule_refresh_embeddings(
        self,
        object_ids: list[str] | None = None,
        *,
        reason: str = "refresh dense embeddings",
        priority: float = 0.3,
    ) -> str:
        """Enqueue a REFRESH_EMBEDDINGS job (Phase β-1).

        Returns the new job_id.
        """
        job = new_offline_job(
            job_kind=OfflineJobKind.REFRESH_EMBEDDINGS,
            payload=RefreshEmbeddingsJobPayload(
                object_ids=object_ids or [],
                reason=reason,
            ),
            priority=priority,
            now=self._clock(),
        )
        self._job_store.enqueue_offline_job(job)
        return job.job_id
