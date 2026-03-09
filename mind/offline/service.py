"""Offline maintenance service built on top of Phase C primitives."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from mind.kernel.retrieval import build_query_embedding
from mind.kernel.store import MemoryStore
from mind.primitives.contracts import PrimitiveExecutionContext, PrimitiveOutcome
from mind.primitives.service import PrimitiveService

from .jobs import (
    OfflineJob,
    OfflineJobKind,
    PromoteSchemaJobPayload,
    ReflectEpisodeJobPayload,
)
from .promotion import assess_schema_promotion


class OfflineMaintenanceError(RuntimeError):
    """Raised when an offline maintenance job cannot be completed safely."""


class OfflineMaintenanceService:
    """Execute Phase E offline jobs against the existing primitive surface."""

    def __init__(
        self,
        store: MemoryStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self._clock = clock or _utc_now
        self._primitive_service = PrimitiveService(
            store,
            clock=self._clock,
            query_embedder=build_query_embedding,
        )

    def process_job(
        self,
        job: OfflineJob,
        *,
        actor: str,
    ) -> dict[str, Any]:
        """Run one offline job and return a structured result payload."""

        if job.job_kind is OfflineJobKind.REFLECT_EPISODE:
            return self._process_reflect_episode(job, actor=actor)
        if job.job_kind is OfflineJobKind.PROMOTE_SCHEMA:
            return self._process_promote_schema(job, actor=actor)
        raise OfflineMaintenanceError(f"unsupported offline job kind '{job.job_kind.value}'")

    def _process_reflect_episode(
        self,
        job: OfflineJob,
        *,
        actor: str,
    ) -> dict[str, Any]:
        payload = ReflectEpisodeJobPayload.model_validate(job.payload)
        result = self._primitive_service.reflect(
            payload.model_dump(mode="json"),
            self._context(actor=actor, budget_scope_id=job.job_id),
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
    ) -> dict[str, Any]:
        payload = PromoteSchemaJobPayload.model_validate(job.payload)
        target_objects = [self.store.read_object(object_id) for object_id in payload.target_refs]
        decision = assess_schema_promotion(target_objects)
        if not decision.promote:
            raise OfflineMaintenanceError(decision.reason)

        reason = f"{payload.reason}; {decision.reason}"
        result = self._primitive_service.reorganize_simple(
            {
                "target_refs": payload.target_refs,
                "operation": "synthesize_schema",
                "reason": reason,
            },
            self._context(actor=actor, budget_scope_id=job.job_id),
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
        }

    @staticmethod
    def _context(
        *,
        actor: str,
        budget_scope_id: str,
    ) -> PrimitiveExecutionContext:
        return PrimitiveExecutionContext(
            actor=actor,
            budget_scope_id=budget_scope_id,
            budget_limit=100.0,
        )


def _primitive_failure_message(error: Any) -> str:
    if error is None:
        return "primitive failed without structured error"
    code = getattr(error, "code", None)
    message = getattr(error, "message", None)
    return f"{code.value if code is not None else 'primitive_error'}: {message}"


def _utc_now() -> datetime:
    return datetime.now(UTC)
