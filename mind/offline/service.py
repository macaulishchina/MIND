"""Offline maintenance service built on top of primitives."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from mind.capabilities import (
    CapabilityService,
    OfflineReconstructRequest,
    resolve_capability_provider_config,
)
from mind.kernel.retrieval import build_query_embedding
from mind.kernel.store import MemoryStore
from mind.primitives.contracts import PrimitiveExecutionContext, PrimitiveOutcome
from mind.primitives.service import PrimitiveService
from mind.telemetry import TelemetryEvent, TelemetryEventKind, TelemetryRecorder, TelemetryScope

from .jobs import (
    OfflineJob,
    OfflineJobKind,
    PromoteSchemaJobPayload,
    ReflectEpisodeJobPayload,
    UpdatePriorityJobPayload,
)
from .promotion import assess_schema_promotion

type ProviderEnvResolver = Callable[[], Mapping[str, str] | None]


class OfflineMaintenanceError(RuntimeError):
    """Raised when an offline maintenance job cannot be completed safely."""


class OfflineMaintenanceService:
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
            capability_service=self._capability_service,
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
                payload = ReflectEpisodeJobPayload.model_validate(job.payload)
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
                            "episode_id": payload.episode_id,
                            "focus": payload.focus,
                        },
                    ),
                )
                result = self._process_reflect_episode(
                    job,
                    actor=actor,
                    payload=payload,
                    dev_mode=dev_mode,
                    provider_selection=provider_selection,
                    telemetry_run_id=run_id,
                    telemetry_operation_id=operation_id,
                    telemetry_parent_event_id=last_parent_event_id,
                )
            elif job.job_kind is OfflineJobKind.PROMOTE_SCHEMA:
                payload = PromoteSchemaJobPayload.model_validate(job.payload)
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
                            "target_refs": list(payload.target_refs),
                            "requested_reason": payload.reason,
                        },
                    ),
                )
                decision, target_objects = self._assess_promotion(payload)
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
                    payload=payload,
                    decision=decision,
                    target_objects=target_objects,
                    dev_mode=dev_mode,
                    provider_selection=provider_selection,
                    telemetry_run_id=run_id,
                    telemetry_operation_id=operation_id,
                    telemetry_parent_event_id=last_parent_event_id,
                )
            elif job.job_kind is OfflineJobKind.UPDATE_PRIORITY:
                payload = UpdatePriorityJobPayload.model_validate(job.payload)
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
                            "object_count": len(payload.object_ids),
                            "reason": payload.reason,
                        },
                    ),
                )
                result = self._process_update_priority(job, payload=payload)
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

    def _process_reflect_episode(
        self,
        job: OfflineJob,
        *,
        actor: str,
        payload: ReflectEpisodeJobPayload,
        dev_mode: bool,
        provider_selection: dict[str, Any] | None,
        telemetry_run_id: str,
        telemetry_operation_id: str,
        telemetry_parent_event_id: str,
    ) -> dict[str, Any]:
        result = self._primitive_service.reflect(
            payload.model_dump(mode="json"),
            self._context(
                actor=actor,
                budget_scope_id=job.job_id,
                dev_mode=dev_mode,
                provider_selection=provider_selection,
                telemetry_run_id=telemetry_run_id,
                telemetry_operation_id=telemetry_operation_id,
                telemetry_parent_event_id=telemetry_parent_event_id,
            ),
        )
        if result.outcome is not PrimitiveOutcome.SUCCESS or result.response is None:
            raise OfflineMaintenanceError(_primitive_failure_message(result.error))
        reflection_object_id = str(result.response["reflection_object_id"])
        reflection = self.store.read_object(reflection_object_id)
        return {
            "job_kind": job.job_kind.value,
            "primitive": "reflect",
            "reflection_object_id": reflection_object_id,
            "source_refs": list(reflection["source_refs"]),
        }

    def _process_promote_schema(
        self,
        job: OfflineJob,
        *,
        actor: str,
        payload: PromoteSchemaJobPayload,
        decision: Any,
        target_objects: list[dict[str, Any]],
        dev_mode: bool,
        provider_selection: dict[str, Any] | None,
        telemetry_run_id: str,
        telemetry_operation_id: str,
        telemetry_parent_event_id: str,
    ) -> dict[str, Any]:
        provider_config = self._capability_provider_config(provider_selection)
        reconstruction = self._capability_service.offline_reconstruct(
            OfflineReconstructRequest(
                request_id=f"offline-promote-{job.job_id}",
                objective=f"{payload.reason}; {decision.reason}",
                evidence_text=_promotion_evidence_text(target_objects),
                episode_ids=list(decision.supporting_episode_ids),
                evidence_refs=list(decision.evidence_refs),
            ),
            provider_config=provider_config,
        )
        result = self._primitive_service.reorganize_simple(
            {
                "target_refs": payload.target_refs,
                "operation": "synthesize_schema",
                "reason": reconstruction.reconstruction_text,
            },
            self._context(
                actor=actor,
                budget_scope_id=job.job_id,
                dev_mode=dev_mode,
                provider_selection=provider_selection,
                telemetry_run_id=telemetry_run_id,
                telemetry_operation_id=telemetry_operation_id,
                telemetry_parent_event_id=telemetry_parent_event_id,
            ),
        )
        if result.outcome is not PrimitiveOutcome.SUCCESS or result.response is None:
            raise OfflineMaintenanceError(_primitive_failure_message(result.error))

        new_object_ids = list(result.response["new_object_ids"])
        if len(new_object_ids) != 1:
            raise OfflineMaintenanceError("promotion must create exactly one SchemaNote")
        latest_schema = self.store.read_object(new_object_ids[0])
        return {
            "job_kind": job.job_kind.value,
            "primitive": "reorganize_simple",
            "schema_object_id": latest_schema["id"],
            "schema_version": latest_schema["version"],
            "supporting_episode_ids": list(decision.supporting_episode_ids),
            "stability_score": latest_schema["metadata"]["stability_score"],
            "source_refs": list(latest_schema["source_refs"]),
            "reconstruction_text": reconstruction.reconstruction_text,
        }

    def _assess_promotion(
        self,
        payload: PromoteSchemaJobPayload,
    ) -> tuple[Any, list[dict[str, Any]]]:
        target_objects = [self.store.read_object(object_id) for object_id in payload.target_refs]
        return assess_schema_promotion(target_objects), target_objects

    def _process_update_priority(
        self,
        job: OfflineJob,
        *,
        payload: UpdatePriorityJobPayload,
    ) -> dict[str, Any]:
        """Batch-refresh decay_score on a set of objects using recency signal."""
        now = self._clock()
        updated_ids: list[str] = []
        object_ids = payload.object_ids or [
            obj["id"] for obj in self.store.iter_latest_objects()
        ]
        for object_id in object_ids:
            try:
                obj = self.store.read_object(object_id)
            except Exception:
                continue
            if obj.get("status") in ("archived", "deprecated", "invalid"):
                continue
            metadata = dict(obj.get("metadata", {}))
            # Compute decay_score based on age since creation
            try:
                created_at = datetime.fromisoformat(
                    str(obj.get("created_at", "")).replace("Z", "+00:00")
                )
                age_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
            except (ValueError, TypeError):
                age_days = 0.0
            # Exponential decay with 90-day half-life
            decay_score = round(math.exp(-age_days / 90.0 * math.log(2)), 4)
            if metadata.get("decay_score") == decay_score:
                continue
            metadata["decay_score"] = decay_score
            updated_obj = dict(obj)
            updated_obj["version"] = int(obj["version"]) + 1
            updated_obj["updated_at"] = now.isoformat()
            updated_obj["metadata"] = metadata
            try:
                self.store.insert_object(updated_obj)
                updated_ids.append(object_id)
            except Exception:
                continue

        return {
            "job_kind": job.job_kind.value,
            "updated_count": len(updated_ids),
            "updated_ids": updated_ids,
            "reason": payload.reason,
        }

    @staticmethod
    def _context(
        *,
        actor: str,
        budget_scope_id: str,
        dev_mode: bool = False,
        provider_selection: dict[str, Any] | None = None,
        telemetry_run_id: str | None = None,
        telemetry_operation_id: str | None = None,
        telemetry_parent_event_id: str | None = None,
    ) -> PrimitiveExecutionContext:
        return PrimitiveExecutionContext(
            actor=actor,
            budget_scope_id=budget_scope_id,
            budget_limit=100.0,
            dev_mode=dev_mode,
            provider_selection=provider_selection,
            telemetry_run_id=telemetry_run_id,
            telemetry_operation_id=telemetry_operation_id,
            telemetry_parent_event_id=telemetry_parent_event_id,
        )

    def _record_telemetry(
        self,
        *,
        enabled: bool,
        event: TelemetryEvent,
    ) -> None:
        if enabled and self._telemetry_recorder is not None:
            self._telemetry_recorder.record(event)

    def _capability_provider_config(
        self,
        provider_selection: dict[str, Any] | None,
    ) -> Any:
        if not provider_selection:
            return None
        try:
            return resolve_capability_provider_config(
                selection=provider_selection,
                env=(
                    self._provider_env_resolver()
                    if self._provider_env_resolver is not None
                    else None
                ),
            )
        except RuntimeError as exc:
            raise OfflineMaintenanceError(str(exc)) from exc


def _primitive_failure_message(error: Any) -> str:
    if error is None:
        return "primitive failed without structured error"
    code = getattr(error, "code", None)
    message = getattr(error, "message", None)
    return f"{code.value if code is not None else 'primitive_error'}: {message}"


def _promotion_evidence_text(target_objects: list[dict[str, Any]]) -> str:
    lines = []
    for obj in target_objects:
        metadata = obj.get("metadata", {})
        episode_id = metadata.get("episode_id") or "-"
        lines.append(
            f"{obj['id']} [{obj['type']}] episode={episode_id}: {_object_signal_text(obj)}"
        )
    return "\n".join(lines)


def _object_signal_text(obj: dict[str, Any]) -> str:
    content = obj.get("content", {})
    for key in ("summary", "text", "rule", "title", "result_summary"):
        value = content.get(key)
        if value:
            return str(value)
    return str(content)[:240]


def _utc_now() -> datetime:
    return datetime.now(UTC)
