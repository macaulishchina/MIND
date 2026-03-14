"""Offline maintenance service built on top of primitives."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from mind.capabilities import CapabilityPortAdapter, CapabilityService
from mind.kernel.retrieval import build_query_embedding
from mind.kernel.store import MemoryStore
from mind.primitives.service import PrimitiveService
from mind.telemetry import TelemetryEvent, TelemetryEventKind, TelemetryRecorder, TelemetryScope

from .jobs import (
    AutoArchiveJobPayload,
    DiscoverLinksJobPayload,
    OfflineJob,
    OfflineJobKind,
    PromotePolicyJobPayload,
    PromotePreferenceJobPayload,
    PromoteSchemaJobPayload,
    RebuildArtifactIndexJobPayload,
    ReflectEpisodeJobPayload,
    RefreshEmbeddingsJobPayload,
    ResolveConflictJobPayload,
    UpdatePriorityJobPayload,
    VerifyProposalJobPayload,
)
from .processors import OfflineMaintenanceError, _OfflineProcessorMixin  # noqa: F401

type ProviderEnvResolver = Callable[[], Mapping[str, str] | None]


class OfflineMaintenanceService(_OfflineProcessorMixin):
    """Execute offline jobs against the existing primitive surface."""

    def __init__(
        self,
        store: MemoryStore,
        *,
        clock: Callable[[], datetime] | None = None,
        capability_service: CapabilityService | None = None,
        telemetry_recorder: TelemetryRecorder | None = None,
        provider_env_resolver: ProviderEnvResolver | None = None,
    ) -> None:
        self.store = store
        self._clock = clock or _utc_now
        self._telemetry_recorder = telemetry_recorder
        self._capability_service = capability_service or CapabilityService(clock=self._clock)
        self._provider_env_resolver = provider_env_resolver
        self._primitive_service = PrimitiveService(
            store,
            clock=self._clock,
            query_embedder=build_query_embedding,
            capability_service=CapabilityPortAdapter(service=self._capability_service),
            telemetry_recorder=telemetry_recorder,
            provider_env_resolver=provider_env_resolver,
        )

    def process_job(
        self,
        job: OfflineJob,
        *,
        actor: str,
        dev_mode: bool = False,
        provider_selection: dict[str, Any] | None = None,
        telemetry_run_id: str | None = None,
    ) -> dict[str, Any]:
        """Run one offline job and return a structured result payload."""

        run_id = telemetry_run_id or f"offline-{job.job_id}"
        operation_id = f"offline-{job.job_kind.value}-{job.job_id}"
        last_parent_event_id = f"{operation_id}-entry"
        self._record_telemetry(
            enabled=dev_mode,
            event=TelemetryEvent(
                event_id=last_parent_event_id,
                scope=TelemetryScope.OFFLINE,
                kind=TelemetryEventKind.ENTRY,
                occurred_at=self._clock(),
                run_id=run_id,
                operation_id=operation_id,
                job_id=job.job_id,
                actor=actor,
                payload={
                    "job_kind": job.job_kind.value,
                    "payload": dict(job.payload),
                    "status": job.status.value,
                },
                debug_fields={
                    "priority": job.priority,
                    "attempt_count": job.attempt_count,
                    "max_attempts": job.max_attempts,
                },
            ),
        )

        try:
            if job.job_kind is OfflineJobKind.REFLECT_EPISODE:
                reflect_payload = ReflectEpisodeJobPayload.model_validate(job.payload)
                last_parent_event_id = f"{operation_id}-dispatch"
                self._record_telemetry(
                    enabled=dev_mode,
                    event=TelemetryEvent(
                        event_id=last_parent_event_id,
                        scope=TelemetryScope.OFFLINE,
                        kind=TelemetryEventKind.DECISION,
                        occurred_at=self._clock(),
                        run_id=run_id,
                        operation_id=operation_id,
                        parent_event_id=f"{operation_id}-entry",
                        job_id=job.job_id,
                        actor=actor,
                        payload={
                            "stage": "dispatch",
                            "job_kind": job.job_kind.value,
                            "handler": "reflect_episode",
                            "primitive": "reflect",
                            "episode_id": reflect_payload.episode_id,
                            "focus": reflect_payload.focus,
                        },
                    ),
                )
                result = self._process_reflect_episode(
                    job,
                    actor=actor,
                    payload=reflect_payload,
                    dev_mode=dev_mode,
                    provider_selection=provider_selection,
                    telemetry_run_id=run_id,
                    telemetry_operation_id=operation_id,
                    telemetry_parent_event_id=last_parent_event_id,
                )
            elif job.job_kind is OfflineJobKind.PROMOTE_SCHEMA:
                schema_payload = PromoteSchemaJobPayload.model_validate(job.payload)
                last_parent_event_id = f"{operation_id}-dispatch"
                self._record_telemetry(
                    enabled=dev_mode,
                    event=TelemetryEvent(
                        event_id=last_parent_event_id,
                        scope=TelemetryScope.OFFLINE,
                        kind=TelemetryEventKind.DECISION,
                        occurred_at=self._clock(),
                        run_id=run_id,
                        operation_id=operation_id,
                        parent_event_id=f"{operation_id}-entry",
                        job_id=job.job_id,
                        actor=actor,
                        payload={
                            "stage": "dispatch",
                            "job_kind": job.job_kind.value,
                            "handler": "promote_schema",
                            "primitive": "reorganize_simple",
                            "target_refs": list(schema_payload.target_refs),
                            "requested_reason": schema_payload.reason,
                        },
                    ),
                )
                decision, target_objects = self._assess_promotion(schema_payload)
                last_parent_event_id = f"{operation_id}-assessment"
                self._record_telemetry(
                    enabled=dev_mode,
                    event=TelemetryEvent(
                        event_id=last_parent_event_id,
                        scope=TelemetryScope.OFFLINE,
                        kind=TelemetryEventKind.DECISION,
                        occurred_at=self._clock(),
                        run_id=run_id,
                        operation_id=operation_id,
                        parent_event_id=f"{operation_id}-dispatch",
                        job_id=job.job_id,
                        actor=actor,
                        payload={
                            "stage": "promotion_assessment",
                            "promote": decision.promote,
                            "reason": decision.reason,
                            "supporting_episode_ids": list(decision.supporting_episode_ids),
                            "evidence_refs": list(decision.evidence_refs),
                        },
                        debug_fields={
                            "target_count": len(target_objects),
                            "supporting_episode_count": len(decision.supporting_episode_ids),
                        },
                    ),
                )
                if not decision.promote:
                    raise OfflineMaintenanceError(decision.reason)
                result = self._process_promote_schema(
                    job,
                    actor=actor,
                    payload=schema_payload,
                    decision=decision,
                    target_objects=target_objects,
                    dev_mode=dev_mode,
                    provider_selection=provider_selection,
                    telemetry_run_id=run_id,
                    telemetry_operation_id=operation_id,
                    telemetry_parent_event_id=last_parent_event_id,
                )
            elif job.job_kind is OfflineJobKind.UPDATE_PRIORITY:
                priority_payload = UpdatePriorityJobPayload.model_validate(job.payload)
                last_parent_event_id = f"{operation_id}-dispatch"
                self._record_telemetry(
                    enabled=dev_mode,
                    event=TelemetryEvent(
                        event_id=last_parent_event_id,
                        scope=TelemetryScope.OFFLINE,
                        kind=TelemetryEventKind.DECISION,
                        occurred_at=self._clock(),
                        run_id=run_id,
                        operation_id=operation_id,
                        parent_event_id=f"{operation_id}-entry",
                        job_id=job.job_id,
                        actor=actor,
                        payload={
                            "stage": "dispatch",
                            "job_kind": job.job_kind.value,
                            "handler": "update_priority",
                            "object_count": len(priority_payload.object_ids),
                            "reason": priority_payload.reason,
                        },
                    ),
                )
                result = self._process_update_priority(job, payload=priority_payload)
            elif job.job_kind is OfflineJobKind.REFRESH_EMBEDDINGS:
                refresh_payload = RefreshEmbeddingsJobPayload.model_validate(job.payload)
                result = self._process_refresh_embeddings(job, payload=refresh_payload)
            elif job.job_kind is OfflineJobKind.RESOLVE_CONFLICT:
                conflict_payload = ResolveConflictJobPayload.model_validate(job.payload)
                result = self._process_resolve_conflict(job, payload=conflict_payload)
            elif job.job_kind is OfflineJobKind.VERIFY_PROPOSAL:
                verify_payload = VerifyProposalJobPayload.model_validate(job.payload)
                result = self._process_verify_proposal(job, payload=verify_payload)
            elif job.job_kind is OfflineJobKind.PROMOTE_POLICY:
                policy_payload = PromotePolicyJobPayload.model_validate(job.payload)
                result = self._process_promote_policy(job, payload=policy_payload)
            elif job.job_kind is OfflineJobKind.PROMOTE_PREFERENCE:
                pref_payload = PromotePreferenceJobPayload.model_validate(job.payload)
                result = self._process_promote_preference(job, payload=pref_payload)
            elif job.job_kind is OfflineJobKind.DISCOVER_LINKS:
                links_payload = DiscoverLinksJobPayload.model_validate(job.payload)
                result = self._process_discover_links(job, payload=links_payload)
            elif job.job_kind is OfflineJobKind.REBUILD_ARTIFACT_INDEX:
                index_payload = RebuildArtifactIndexJobPayload.model_validate(job.payload)
                result = self._process_rebuild_artifact_index(job, payload=index_payload)
            elif job.job_kind is OfflineJobKind.AUTO_ARCHIVE:
                archive_payload = AutoArchiveJobPayload.model_validate(job.payload)
                result = self._process_auto_archive(job, payload=archive_payload)
            else:
                raise OfflineMaintenanceError(
                    f"unsupported offline job kind '{job.job_kind.value}'"
                )
        except Exception as exc:
            self._record_telemetry(
                enabled=dev_mode,
                event=TelemetryEvent(
                    event_id=f"{operation_id}-result",
                    scope=TelemetryScope.OFFLINE,
                    kind=TelemetryEventKind.ACTION_RESULT,
                    occurred_at=self._clock(),
                    run_id=run_id,
                    operation_id=operation_id,
                    parent_event_id=last_parent_event_id,
                    job_id=job.job_id,
                    actor=actor,
                    payload={
                        "outcome": "failure",
                        "job_kind": job.job_kind.value,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    },
                ),
            )
            raise

        self._record_telemetry(
            enabled=dev_mode,
            event=TelemetryEvent(
                event_id=f"{operation_id}-result",
                scope=TelemetryScope.OFFLINE,
                kind=TelemetryEventKind.ACTION_RESULT,
                occurred_at=self._clock(),
                run_id=run_id,
                operation_id=operation_id,
                parent_event_id=last_parent_event_id,
                job_id=job.job_id,
                actor=actor,
                payload={
                    "outcome": "success",
                    "job_kind": job.job_kind.value,
                    "result": result,
                },
                debug_fields={
                    "result_keys": sorted(result),
                },
            ),
        )
        return result


def _utc_now() -> datetime:
    return datetime.now(UTC)
