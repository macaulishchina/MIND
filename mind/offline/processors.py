"""Offline maintenance job processors (extracted from service.py)."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any

from mind.capabilities import OfflineReconstructRequest, resolve_capability_provider_config
from mind.kernel.store import MemoryStore
from mind.primitives.contracts import PrimitiveExecutionContext, PrimitiveOutcome
from mind.primitives.service import PrimitiveService
from mind.telemetry import TelemetryEvent, TelemetryRecorder

from .jobs import (
    AutoArchiveJobPayload,
    DiscoverLinksJobPayload,
    OfflineJob,
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
from .promotion import (
    assess_policy_promotion,
    assess_preference_promotion,
    assess_schema_promotion,
)

if TYPE_CHECKING:
    from mind.capabilities import CapabilityService

type ProviderEnvResolver = Callable[[], Mapping[str, str] | None]


class OfflineMaintenanceError(RuntimeError):
    """Raised when an offline maintenance job cannot be completed safely."""


class _OfflineProcessorMixin:
    """Mixin containing all job processor methods for OfflineMaintenanceService."""

    store: MemoryStore
    _clock: Any
    _primitive_service: PrimitiveService
    _capability_service: CapabilityService
    _provider_env_resolver: Any
    _telemetry_recorder: TelemetryRecorder | None

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

        # Phase β-4: Set proposal_status=proposed on the new SchemaNote so that
        # it must pass VERIFY_PROPOSAL before entering retrieval.
        schema_obj = self.store.read_object(new_object_ids[0])
        now = self._clock()
        updated_metadata = dict(schema_obj.get("metadata", {}))
        updated_metadata["proposal_status"] = "proposed"
        updated_schema = dict(schema_obj)
        updated_schema["version"] = int(schema_obj["version"]) + 1
        updated_schema["updated_at"] = now.isoformat()
        updated_schema["metadata"] = updated_metadata
        self.store.insert_object(updated_schema)
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
            "proposal_status": "proposed",
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
        object_ids = payload.object_ids or [obj["id"] for obj in self.store.iter_latest_objects()]
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

    def _process_refresh_embeddings(
        self,
        job: OfflineJob,
        *,
        payload: RefreshEmbeddingsJobPayload,
    ) -> dict[str, Any]:
        """Batch-refresh dense embeddings for objects that lack them (Phase β-1)."""
        from mind.kernel.embedding import embed_objects

        now = self._clock()
        object_ids = payload.object_ids or [obj["id"] for obj in self.store.iter_latest_objects()]
        refreshed_ids: list[str] = []
        target_objects: list[dict[str, Any]] = []
        for object_id in object_ids:
            try:
                obj = self.store.read_object(object_id)
            except Exception:
                continue
            if obj.get("status") in ("archived", "deprecated", "invalid"):
                continue
            # Only refresh objects that don't already have dense_embedding.
            if obj.get("metadata", {}).get("dense_embedding_refreshed"):
                continue
            target_objects.append(obj)

        if not target_objects:
            return {
                "job_kind": job.job_kind.value,
                "refreshed_count": 0,
                "refreshed_ids": [],
                "reason": payload.reason,
            }

        embeddings = embed_objects(target_objects)
        for obj in target_objects:
            try:
                embedding = embeddings.get(obj["id"])
                if embedding is None:
                    continue
                metadata = dict(obj.get("metadata", {}))
                metadata["dense_embedding_refreshed"] = True
                metadata["dense_embedding_dim"] = len(embedding)
                updated_obj = dict(obj)
                updated_obj["version"] = int(obj["version"]) + 1
                updated_obj["updated_at"] = now.isoformat()
                updated_obj["metadata"] = metadata
                self.store.insert_object(updated_obj)
                refreshed_ids.append(obj["id"])
            except Exception:
                continue

        return {
            "job_kind": job.job_kind.value,
            "refreshed_count": len(refreshed_ids),
            "refreshed_ids": refreshed_ids,
            "reason": payload.reason,
        }

    def _process_resolve_conflict(
        self,
        job: OfflineJob,
        *,
        payload: ResolveConflictJobPayload,
    ) -> dict[str, Any]:
        """Handle conflict resolution for a flagged object (Phase β-2)."""
        from mind.primitives.conflict import ConflictRelation

        now = self._clock()
        deprecated_ids: list[str] = []
        high_confidence_contradictions = [
            c
            for c in payload.conflict_candidates
            if (
                c.get("relation") == ConflictRelation.CONTRADICT
                and float(c.get("confidence", 0.0)) >= 0.85
            )
        ]
        for candidate in high_confidence_contradictions:
            neighbour_id = candidate.get("neighbor_id")
            if not neighbour_id:
                continue
            try:
                neighbour = self.store.read_object(neighbour_id)
            except Exception:
                continue
            if neighbour.get("status") in ("archived", "deprecated", "invalid"):
                continue
            metadata = dict(neighbour.get("metadata", {}))
            metadata["deprecated_by"] = payload.object_id
            metadata["deprecation_reason"] = candidate.get("explanation", "conflict resolved")
            deprecated_obj = dict(neighbour)
            deprecated_obj["status"] = "deprecated"
            deprecated_obj["version"] = int(neighbour["version"]) + 1
            deprecated_obj["updated_at"] = now.isoformat()
            deprecated_obj["metadata"] = metadata
            try:
                self.store.insert_object(deprecated_obj)
                deprecated_ids.append(neighbour_id)
            except Exception:
                continue

        return {
            "job_kind": job.job_kind.value,
            "object_id": payload.object_id,
            "deprecated_count": len(deprecated_ids),
            "deprecated_ids": deprecated_ids,
        }

    def _process_verify_proposal(
        self,
        job: OfflineJob,
        *,
        payload: VerifyProposalJobPayload,
    ) -> dict[str, Any]:
        """Verify or reject a proposed SchemaNote (Phase β-4).

        Simple rule-based verification:
        * If the SchemaNote has cross-episode evidence (>= 2 distinct episodes),
          it is promoted to ``committed``.
        * Otherwise it is ``rejected``.
        """
        now = self._clock()
        try:
            schema_note = self.store.read_object(payload.schema_note_id)
        except Exception as exc:
            raise OfflineMaintenanceError(
                f"schema note '{payload.schema_note_id}' not found"
            ) from exc

        if schema_note.get("type") != "SchemaNote":
            raise OfflineMaintenanceError(f"object '{payload.schema_note_id}' is not a SchemaNote")

        metadata = schema_note.get("metadata", {})
        evidence_refs = metadata.get("evidence_refs", [])
        supporting_episode_ids = set()
        for ref in evidence_refs:
            try:
                ref_obj = self.store.read_object(ref)
                ep_id = ref_obj.get("metadata", {}).get("episode_id")
                if ep_id:
                    supporting_episode_ids.add(ep_id)
            except Exception:
                continue

        # Verification decision: require cross-episode support.
        verified = len(supporting_episode_ids) >= 2
        new_proposal_status = "committed" if verified else "rejected"

        updated_metadata = dict(metadata)
        updated_metadata["proposal_status"] = new_proposal_status
        updated_obj = dict(schema_note)
        updated_obj["version"] = int(schema_note["version"]) + 1
        updated_obj["updated_at"] = now.isoformat()
        updated_obj["metadata"] = updated_metadata
        try:
            self.store.insert_object(updated_obj)
        except Exception as exc:
            raise OfflineMaintenanceError(
                f"failed to update proposal status for '{payload.schema_note_id}'"
            ) from exc

        return {
            "job_kind": job.job_kind.value,
            "schema_note_id": payload.schema_note_id,
            "proposal_status": new_proposal_status,
            "supporting_episodes": sorted(supporting_episode_ids),
            "verified": verified,
        }

    def _process_promote_policy(
        self,
        job: OfflineJob,
        *,
        payload: PromotePolicyJobPayload,
    ) -> dict[str, Any]:
        """Promote a set of objects into a PolicyNote (Phase γ-1)."""
        target_objects = [self.store.read_object(ref) for ref in payload.target_refs]
        decision = assess_policy_promotion(target_objects)
        if not decision.promote:
            raise OfflineMaintenanceError(decision.reason)
        now = self._clock()
        ts = now.isoformat()
        from uuid import uuid4

        policy_id = f"policy-{uuid4().hex}"
        policy_note = {
            "id": policy_id,
            "type": "PolicyNote",
            "content": {
                "summary": payload.reason,
                "evidence_ids": list(decision.evidence_refs),
            },
            "source_refs": list(decision.evidence_refs),
            "created_at": ts,
            "updated_at": ts,
            "version": 1,
            "status": "active",
            "priority": round(decision.stability_score, 4),
            "metadata": {
                "trigger_condition": "convergent_episodes",
                "action_pattern": payload.reason,
                "evidence_refs": list(decision.evidence_refs),
                "confidence": decision.stability_score,
                "applies_to_scope": "general",
                "supporting_episode_ids": list(decision.supporting_episode_ids),
                "proposal_status": "proposed",
            },
        }
        self.store.insert_object(policy_note)
        return {
            "job_kind": job.job_kind.value,
            "policy_note_id": policy_id,
            "supporting_episode_ids": list(decision.supporting_episode_ids),
            "stability_score": decision.stability_score,
            "proposal_status": "proposed",
        }

    def _process_promote_preference(
        self,
        job: OfflineJob,
        *,
        payload: PromotePreferenceJobPayload,
    ) -> dict[str, Any]:
        """Promote a set of objects into a PreferenceNote (Phase γ-1)."""
        target_objects = [self.store.read_object(ref) for ref in payload.target_refs]
        decision = assess_preference_promotion(target_objects)
        if not decision.promote:
            raise OfflineMaintenanceError(decision.reason)
        now = self._clock()
        ts = now.isoformat()
        from uuid import uuid4

        pref_id = f"preference-{uuid4().hex}"
        preference_note = {
            "id": pref_id,
            "type": "PreferenceNote",
            "content": {
                "summary": payload.reason,
                "evidence_ids": list(decision.evidence_refs),
            },
            "source_refs": list(decision.evidence_refs),
            "created_at": ts,
            "updated_at": ts,
            "version": 1,
            "status": "active",
            "priority": round(decision.stability_score, 4),
            "metadata": {
                "preference_key": payload.reason,
                "preference_value": "inferred",
                "strength": round(decision.stability_score, 4),
                "evidence_refs": list(decision.evidence_refs),
                "supporting_episode_ids": list(decision.supporting_episode_ids),
            },
        }
        self.store.insert_object(preference_note)
        return {
            "job_kind": job.job_kind.value,
            "preference_note_id": pref_id,
            "supporting_episode_ids": list(decision.supporting_episode_ids),
            "stability_score": decision.stability_score,
        }

    def _process_discover_links(
        self,
        job: OfflineJob,
        *,
        payload: DiscoverLinksJobPayload,
    ) -> dict[str, Any]:
        """Automatically discover and create proposed LinkEdge objects (Phase γ-2)."""
        import math
        from uuid import uuid4

        from mind.kernel.embedding import embed_objects

        now = self._clock()
        ts = now.isoformat()
        object_ids = payload.object_ids or [
            obj["id"] for obj in self.store.iter_latest_objects(statuses=("active",))
        ]
        # Only process high-priority objects to keep cost low.
        candidates: list[dict[str, Any]] = []
        for oid in object_ids:
            try:
                obj = self.store.read_object(oid)
            except Exception:
                continue
            if obj.get("status") != "active":
                continue
            if obj.get("type") in ("LinkEdge", "WorkspaceView", "FeedbackRecord"):
                continue
            candidates.append(obj)

        embeddings = embed_objects(candidates)
        # Compute cosine similarity between all pairs.
        created_links: list[str] = []
        obj_ids = [obj["id"] for obj in candidates]
        for i, src_obj in enumerate(candidates):
            src_vec = embeddings.get(src_obj["id"])
            if src_vec is None:
                continue
            src_norm = math.sqrt(sum(v * v for v in src_vec))
            if src_norm == 0:
                continue
            similarities: list[tuple[float, str]] = []
            for j, dst_obj in enumerate(candidates):
                if j <= i:
                    continue
                dst_vec = embeddings.get(dst_obj["id"])
                if dst_vec is None:
                    continue
                dst_norm = math.sqrt(sum(v * v for v in dst_vec))
                if dst_norm == 0:
                    continue
                dot = sum(a * b for a, b in zip(src_vec, dst_vec, strict=False))
                sim = dot / (src_norm * dst_norm)
                if sim >= payload.min_similarity:
                    similarities.append((sim, dst_obj["id"]))
            similarities.sort(reverse=True)
            for sim, dst_id in similarities[: payload.top_k]:
                link_id = f"link-{src_obj['id']}-{dst_id}-{uuid4().hex[:8]}"
                link = {
                    "id": link_id,
                    "type": "LinkEdge",
                    "content": {
                        "src_id": src_obj["id"],
                        "dst_id": dst_id,
                        "relation_type": "similar",
                    },
                    "source_refs": [src_obj["id"], dst_id],
                    "created_at": ts,
                    "updated_at": ts,
                    "version": 1,
                    "status": "active",
                    "priority": round(sim, 4),
                    "metadata": {
                        "confidence": round(sim, 4),
                        "evidence_refs": [src_obj["id"], dst_id],
                        "discovery_method": "embedding_similarity",
                        "proposal_status": "proposed",
                    },
                }
                try:
                    self.store.insert_object(link)
                    created_links.append(link_id)
                except Exception:
                    continue

        _ = obj_ids  # suppress unused variable warning
        return {
            "job_kind": job.job_kind.value,
            "created_links": len(created_links),
            "link_ids": created_links,
            "candidate_count": len(candidates),
        }

    def _process_rebuild_artifact_index(
        self,
        job: OfflineJob,
        *,
        payload: RebuildArtifactIndexJobPayload,
    ) -> dict[str, Any]:
        """Rebuild the ArtifactIndex tree for long objects (Phase γ-4)."""
        from .artifact_indexer import build_artifact_index

        now = self._clock()
        object_ids = payload.object_ids or [
            obj["id"] for obj in self.store.iter_latest_objects(statuses=("active",))
        ]
        indexed_ids: list[str] = []
        index_object_ids: list[str] = []
        for oid in object_ids:
            try:
                obj = self.store.read_object(oid)
            except Exception:
                continue
            if obj.get("status") != "active":
                continue
            if obj.get("type") in ("WorkspaceView", "ArtifactIndex", "LinkEdge"):
                continue
            artifact_objects = build_artifact_index(
                obj,
                min_content_length=payload.min_content_length,
                now=now,
            )
            if not artifact_objects:
                continue
            for artifact in artifact_objects:
                try:
                    self.store.insert_object(artifact)
                    index_object_ids.append(artifact["id"])
                except Exception:
                    continue
            indexed_ids.append(oid)

        return {
            "job_kind": job.job_kind.value,
            "indexed_count": len(indexed_ids),
            "indexed_ids": indexed_ids,
            "index_object_count": len(index_object_ids),
            "reason": payload.reason,
        }

    def _process_auto_archive(
        self,
        job: OfflineJob,
        *,
        payload: AutoArchiveJobPayload,
    ) -> dict[str, Any]:
        """Archive stale objects that have had no positive feedback (Phase γ-5)."""
        now = self._clock()
        archived_ids: list[str] = []
        eligible_types = {"RawRecord", "SummaryNote"}
        all_objects = self.store.iter_latest_objects(statuses=("active",))
        for obj in all_objects:
            if obj.get("type") not in eligible_types:
                continue
            metadata = obj.get("metadata", {})
            # Skip objects that have positive feedback.
            if int(metadata.get("feedback_positive_count", 0)) > 0:
                continue
            # Compute age since creation.
            try:
                created_at = datetime.fromisoformat(
                    str(obj.get("created_at", "")).replace("Z", "+00:00")
                )
                age_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
            except (ValueError, TypeError):
                age_days = 0.0
            if age_days < payload.stale_days:
                continue
            if payload.dry_run:
                archived_ids.append(obj["id"])
                continue
            # Archive the object.
            updated_metadata = dict(metadata)
            updated_metadata["auto_archived_at"] = now.isoformat()
            updated_metadata["auto_archive_reason"] = payload.reason
            updated_obj = dict(obj)
            updated_obj["status"] = "archived"
            updated_obj["version"] = int(obj["version"]) + 1
            updated_obj["updated_at"] = now.isoformat()
            updated_obj["metadata"] = updated_metadata
            try:
                self.store.insert_object(updated_obj)
                archived_ids.append(obj["id"])
            except Exception:
                continue

        return {
            "job_kind": job.job_kind.value,
            "archived_count": len(archived_ids),
            "archived_ids": archived_ids,
            "dry_run": payload.dry_run,
            "stale_days": payload.stale_days,
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


