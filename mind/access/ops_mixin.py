"""Access service operations mixin (extracted from AccessService)."""

# mypy: disable-error-code="attr-defined"

from __future__ import annotations

import json
from typing import Any

from mind.capabilities import AnswerRequest as CapabilityAnswerRequest
from mind.capabilities import CapabilityService, resolve_capability_provider_config
from mind.kernel.store import MemoryStore, StoreError
from mind.primitives.contracts import (
    PrimitiveExecutionContext,
    PrimitiveExecutionResult,
    PrimitiveOutcome,
    ReadResponse,
    RetrieveResponse,
)
from mind.telemetry import TelemetryEvent, TelemetryEventKind, TelemetryRecorder, TelemetryScope

from .contracts import (
    AccessContextKind,
    AccessMode,
    AccessModeTraceEvent,
    AccessReasonCode,
    AccessRunRequest,
    AccessRunResponse,
    AccessRunTrace,
    AccessSwitchKind,
    AccessTaskFamily,
    AccessTraceKind,
    EvidenceSummaryItem,
)
from .service import (
    AccessServiceError,
    _access_action_summary,
    _anchor_priority,
    _answer_question_text,
    _constraints_require_deeper_context,
    _ModeExecution,
    _ModePlan,
    _query_text,
)


class _AccessOpsMixin:
    """Mixin providing retrieval, response building, and tracing operations."""

    store: MemoryStore
    _clock: Any
    _primitive_service: Any
    _capability_service: CapabilityService
    _telemetry_recorder: TelemetryRecorder | None
    _auto_concealment_enabled: bool
    _object_hard_limit: int

    def _record_access_trace(
        self,
        *,
        response: AccessRunResponse,
        actor: str,
        enabled: bool,
        run_id: str,
        operation_id: str,
    ) -> None:
        decision_events = [
            event
            for event in response.trace.events
            if event.event_kind is AccessTraceKind.SELECT_MODE
        ]
        parent_event_id = f"{operation_id}-entry"
        for index, decision in enumerate(decision_events, start=1):
            event_id = f"{operation_id}-decision-{index}"
            self._record_access_telemetry(
                enabled=enabled,
                event=TelemetryEvent(
                    event_id=event_id,
                    scope=TelemetryScope.ACCESS,
                    kind=TelemetryEventKind.DECISION,
                    occurred_at=self._clock(),
                    run_id=run_id,
                    operation_id=operation_id,
                    parent_event_id=parent_event_id,
                    actor=actor,
                    payload={
                        "mode": decision.mode.value,
                        "reason_code": decision.reason_code.value if decision.reason_code else None,
                        "switch_kind": decision.switch_kind.value if decision.switch_kind else None,
                        "from_mode": decision.from_mode.value if decision.from_mode else None,
                        "target_ids": list(decision.target_ids),
                    },
                    debug_fields={"summary": decision.summary},
                ),
            )
            parent_event_id = event_id

        self._record_access_telemetry(
            enabled=enabled,
            event=TelemetryEvent(
                event_id=f"{operation_id}-context",
                scope=TelemetryScope.ACCESS,
                kind=TelemetryEventKind.CONTEXT_RESULT,
                occurred_at=self._clock(),
                run_id=run_id,
                operation_id=operation_id,
                parent_event_id=parent_event_id,
                actor=actor,
                payload={
                    "context_kind": response.context_kind.value,
                    "context_object_ids": list(response.context_object_ids),
                    "candidate_ids": list(response.candidate_ids),
                    "selected_object_ids": list(response.selected_object_ids),
                    "verification_notes": list(response.verification_notes),
                },
                debug_fields={
                    "candidate_count": len(response.candidate_ids),
                    "read_count": len(response.read_object_ids),
                    "selected_count": len(response.selected_object_ids),
                    "context_token_count": response.context_token_count,
                },
            ),
        )
        self._record_access_telemetry(
            enabled=enabled,
            event=TelemetryEvent(
                event_id=f"{operation_id}-result",
                scope=TelemetryScope.ACCESS,
                kind=TelemetryEventKind.ACTION_RESULT,
                occurred_at=self._clock(),
                run_id=run_id,
                operation_id=operation_id,
                parent_event_id=f"{operation_id}-context",
                actor=actor,
                payload={
                    "resolved_mode": response.resolved_mode.value,
                    "trace_summary": response.trace.events[-1].summary,
                    "answer_text": response.answer_text,
                    "answer_support_ids": list(response.answer_support_ids),
                    "answer_trace": dict(response.answer_trace or {}),
                    "summary": _access_action_summary(
                        response.resolved_mode.value,
                        response.answer_text,
                    ),
                },
                debug_fields={
                    "trace_event_count": len(response.trace.events),
                    "expanded_read_count": len(response.expanded_object_ids),
                    "answer_length": len(response.answer_text or ""),
                    "answer_support_count": len(response.answer_support_ids),
                },
            ),
        )

    def _record_access_telemetry(
        self,
        *,
        enabled: bool,
        event: TelemetryEvent,
    ) -> None:
        if not enabled or self._telemetry_recorder is None:
            return
        self._telemetry_recorder.record(event)

    def _choose_initial_auto_mode(
        self,
        request: AccessRunRequest,
        *,
        scout_ids: list[str] | None = None,
    ) -> tuple[AccessMode, AccessReasonCode]:
        # β-5.2: scouting-driven decisions take priority over static rules
        if scout_ids is not None:
            if len(scout_ids) == 0:
                return AccessMode.FLASH, AccessReasonCode.LATENCY_SENSITIVE
            scout_objects = []
            for oid in scout_ids[:3]:
                if self.store.has_object(oid):
                    scout_objects.append(self.store.read_object(oid))
            episodes = {obj.get("metadata", {}).get("episode_id") for obj in scout_objects}
            episodes.discard(None)
            has_conflict = any(
                obj.get("metadata", {}).get("conflict_candidates") for obj in scout_objects
            )
            if has_conflict:
                return AccessMode.RECONSTRUCT, AccessReasonCode.EVIDENCE_CONFLICT
            if len(episodes) > 1:
                return AccessMode.RECONSTRUCT, AccessReasonCode.CONSTRAINT_RISK

        # Existing static rules as fallback
        if request.task_family is AccessTaskFamily.HIGH_CORRECTNESS:
            return AccessMode.RECONSTRUCT, AccessReasonCode.HIGH_CORRECTNESS_REQUIRED
        if request.task_family is AccessTaskFamily.BALANCED:
            return AccessMode.RECALL, AccessReasonCode.BALANCED_DEFAULT
        if request.task_family is AccessTaskFamily.SPEED_SENSITIVE:
            if request.time_budget_ms is not None and request.time_budget_ms <= 200:
                return AccessMode.FLASH, AccessReasonCode.LATENCY_SENSITIVE
            return AccessMode.RECALL, AccessReasonCode.BALANCED_DEFAULT
        if request.hard_constraints:
            return AccessMode.RECONSTRUCT, AccessReasonCode.CONSTRAINT_RISK
        return AccessMode.RECALL, AccessReasonCode.BALANCED_DEFAULT

    def _choose_auto_switch(
        self,
        request: AccessRunRequest,
        execution: _ModeExecution,
    ) -> tuple[AccessMode, AccessReasonCode, AccessSwitchKind] | None:
        if execution.mode is AccessMode.FLASH:
            if _constraints_require_deeper_context(request.hard_constraints):
                return (
                    AccessMode.RECALL,
                    AccessReasonCode.CONSTRAINT_RISK,
                    AccessSwitchKind.UPGRADE,
                )
            if request.task_family is AccessTaskFamily.SPEED_SENSITIVE:
                return None
            if len(execution.candidate_ids) > 1:
                return (
                    AccessMode.RECALL,
                    AccessReasonCode.COVERAGE_INSUFFICIENT,
                    AccessSwitchKind.UPGRADE,
                )
            return None

        if execution.mode is AccessMode.RECALL:
            if (
                request.task_family is AccessTaskFamily.SPEED_SENSITIVE
                and not request.hard_constraints
                and execution.simple_enough
            ):
                return (
                    AccessMode.FLASH,
                    AccessReasonCode.QUALITY_SATISFIED,
                    AccessSwitchKind.DOWNGRADE,
                )
            return None

        if execution.mode is AccessMode.RECONSTRUCT:
            if execution.has_reflection_signal:
                return (
                    AccessMode.REFLECTIVE_ACCESS,
                    AccessReasonCode.EVIDENCE_CONFLICT,
                    AccessSwitchKind.JUMP,
                )
            if request.hard_constraints:
                return (
                    AccessMode.REFLECTIVE_ACCESS,
                    AccessReasonCode.CONSTRAINT_RISK,
                    AccessSwitchKind.JUMP,
                )
            return None

        return None

    def _retrieve(
        self,
        request: AccessRunRequest,
        context: PrimitiveExecutionContext,
        plan: _ModePlan,
    ) -> RetrieveResponse:
        result = self._primitive_service.retrieve(
            {
                "query": request.query,
                "query_modes": [mode.value for mode in request.query_modes],
                "budget": {"max_candidates": plan.retrieve_limit},
                "filters": request.filters.model_dump(mode="json"),
            },
            context,
        )
        return self._require_retrieve_success(result)

    def _enrich_candidates(
        self,
        *,
        mode: AccessMode,
        request: AccessRunRequest,
        candidate_ids: list[str],
        candidate_scores: list[float],
    ) -> tuple[list[str], list[float]]:
        if mode is AccessMode.FLASH:
            return candidate_ids, candidate_scores
        episode_id = request.filters.episode_id
        if episode_id is None:
            return candidate_ids, candidate_scores

        max_score = max(candidate_scores, default=1.0)
        ranked: dict[str, float] = {
            object_id: float(candidate_scores[index])
            for index, object_id in enumerate(candidate_ids)
        }
        for offset, object_id in enumerate(
            self._episode_anchor_ids(episode_id=episode_id, mode=mode),
            start=1,
        ):
            ranked[object_id] = max(
                ranked.get(object_id, 0.0),
                max_score + (0.05 * float(len(ranked) + offset)),
            )

        ordered = sorted(
            ranked.items(),
            key=lambda item: (item[1], item[0]),
            reverse=True,
        )
        return [item[0] for item in ordered], [round(item[1], 4) for item in ordered]

    def _episode_anchor_ids(
        self,
        *,
        episode_id: str,
        mode: AccessMode,
    ) -> list[str]:
        anchor_types = ["TaskEpisode", "SummaryNote"]
        if mode is AccessMode.REFLECTIVE_ACCESS:
            anchor_types.append("ReflectionNote")
        episode_raw_ids = {str(obj["id"]) for obj in self.store.raw_records_for_episode(episode_id)}
        candidates = [
            obj
            for obj in self.store.iter_latest_objects(object_types=anchor_types)
            if (
                obj["id"] == episode_id
                or obj.get("metadata", {}).get("episode_id") == episode_id
                or episode_id in obj.get("source_refs", [])
                or bool(episode_raw_ids.intersection(set(obj.get("source_refs", []))))
            )
        ]
        ranked = sorted(
            candidates,
            key=lambda obj: (
                _anchor_priority(obj["type"]),
                obj["updated_at"],
                obj["id"],
            ),
            reverse=True,
        )
        return [str(obj["id"]) for obj in ranked]

    def _read_objects(
        self,
        object_ids: list[str],
        context: PrimitiveExecutionContext,
    ) -> list[Any]:
        if not object_ids:
            return []
        result = self._primitive_service.read({"object_ids": object_ids}, context)
        response = self._require_read_success(result)
        return list(response.objects)

    @staticmethod
    def _with_telemetry_context(
        context: PrimitiveExecutionContext,
        *,
        operation_id: str,
        parent_event_id: str,
    ) -> PrimitiveExecutionContext:
        return context.model_copy(
            update={
                "telemetry_operation_id": operation_id,
                "telemetry_parent_event_id": parent_event_id,
            }
        )

    @staticmethod
    def _workspace_scores(
        *,
        workspace_candidate_ids: list[str],
        candidate_ids: list[str],
        candidate_scores: list[float],
    ) -> list[float]:
        score_map = {
            object_id: candidate_scores[index] for index, object_id in enumerate(candidate_ids)
        }
        return [float(score_map.get(object_id, 0.0)) for object_id in workspace_candidate_ids]

    def _expand_source_refs(
        self,
        objects: list[Any],
        *,
        limit: int,
        exclude_ids: set[str],
    ) -> list[str]:
        expanded_ids: list[str] = []
        for obj in objects:
            for ref in obj.source_refs:
                if ref in exclude_ids or ref in expanded_ids:
                    continue
                if not self._is_accessible(ref):
                    continue
                expanded_ids.append(ref)
                if len(expanded_ids) >= limit:
                    return expanded_ids
        return expanded_ids

    def _is_accessible(self, object_id: str) -> bool:
        try:
            obj = self.store.read_object(object_id)
        except StoreError:
            return False
        is_concealed = getattr(self.store, "is_object_concealed", None)
        if is_concealed is not None and bool(is_concealed(object_id)):
            return False
        return str(obj["status"]) != "invalid"

    def _graph_expand(
        self,
        candidate_ids: list[str],
        candidate_scores: list[float],
        hops: int,
    ) -> tuple[list[str], list[float]]:
        """Expand candidate IDs via the LinkEdge adjacency graph (Phase γ-2).

        New IDs receive a score slightly below the minimum seed score so they
        do not displace high-quality retrieval results but are still considered.
        Concealed objects are excluded via :meth:`_is_accessible`.
        """
        from mind.kernel.graph import build_adjacency_index, expand_by_graph

        try:
            adjacency = build_adjacency_index(self.store)
        except Exception:
            return candidate_ids, candidate_scores

        new_ids = expand_by_graph(
            candidate_ids,
            adjacency,
            hops=hops,
            max_expand=10,
        )
        # Filter to accessible, non-duplicate IDs.
        existing = set(candidate_ids)
        min_score = min(candidate_scores, default=0.0)
        graph_score = max(0.0, round(min_score - 0.05, 4))
        for nid in new_ids:
            if nid in existing:
                continue
            if not self._is_accessible(nid):
                continue
            candidate_ids.append(nid)
            candidate_scores.append(graph_score)
            existing.add(nid)
        return candidate_ids, candidate_scores

    def _expand_artifact_index(
        self,
        objects: list[Any],
        *,
        limit: int,
        exclude_ids: set[str],
    ) -> list[str]:
        """Drill down into ArtifactIndex children for tree-guided retrieval (Phase γ-4.3).

        When a retrieved object is an ArtifactIndex, find child sections
        (ArtifactIndex objects whose ``parent_object_id`` matches) and return
        their IDs for expanded reading.
        """
        parent_ids: set[str] = set()
        for obj in objects:
            obj_type = getattr(obj, "type", None) or (
                obj.get("type") if isinstance(obj, dict) else None
            )
            if obj_type == "ArtifactIndex":
                oid = getattr(obj, "id", None) or (obj.get("id") if isinstance(obj, dict) else None)
                if oid:
                    parent_ids.add(oid)
        if not parent_ids:
            return []

        child_ids: list[str] = []
        try:
            all_objects = self.store.iter_latest_objects(statuses=("active",))
        except Exception:
            return []
        for obj in all_objects:
            if obj.get("type") != "ArtifactIndex":
                continue
            parent = obj.get("metadata", {}).get("parent_object_id")
            if parent in parent_ids and obj["id"] not in exclude_ids:
                child_ids.append(obj["id"])
                if len(child_ids) >= limit:
                    break
        return child_ids

    @staticmethod
    def _verification_notes(
        *,
        selected_objects: list[Any],
        verification_objects: list[Any],
    ) -> list[str]:
        all_objects = selected_objects + verification_objects
        object_types = sorted({obj.type for obj in all_objects})
        notes: list[str] = [f"checked {len(all_objects)} objects across {len(object_types)} types"]
        if "ReflectionNote" in object_types:
            notes.append("reflection evidence checked")
        if "SchemaNote" in object_types:
            notes.append("schema evidence checked")
        if any(obj.source_refs for obj in all_objects if obj.type != "RawRecord"):
            notes.append("support chains traced to source refs")
        return notes

    def _has_reflection_signal(
        self,
        objects: list[Any],
        query: str | dict[str, Any],
    ) -> bool:
        if any(obj.type == "ReflectionNote" for obj in objects):
            return True
        query_text = _query_text(query)
        if any(term in query_text for term in ("stale", "failed", "conflict", "revalidate")):
            return True
        return False

    @staticmethod
    def _select_event(
        *,
        mode: AccessMode,
        reason_code: AccessReasonCode,
        switch_kind: AccessSwitchKind,
        summary: str,
        from_mode: AccessMode | None = None,
    ) -> AccessModeTraceEvent:
        return AccessModeTraceEvent(
            event_kind=AccessTraceKind.SELECT_MODE,
            mode=mode,
            summary=summary,
            reason_code=reason_code,
            switch_kind=switch_kind,
            from_mode=from_mode,
        )

    @staticmethod
    def _mode_summary_event(
        *,
        mode: AccessMode,
        candidate_ids: tuple[str, ...],
        read_object_ids: tuple[str, ...],
        context_object_ids: tuple[str, ...],
    ) -> AccessModeTraceEvent:
        return AccessModeTraceEvent(
            event_kind=AccessTraceKind.MODE_SUMMARY,
            mode=mode,
            summary=(
                f"{mode.value} completed with {len(candidate_ids)} candidates, "
                f"{len(read_object_ids)} reads, {len(context_object_ids)} context objects"
            ),
            target_ids=list(context_object_ids),
        )

    @staticmethod
    def _candidate_summaries(
        summaries: list[dict[str, Any]],
        candidate_ids: list[str],
        candidate_scores: list[float],
    ) -> list[dict[str, Any]]:
        summary_map = {
            str(item.get("object_id")): dict(item)
            for item in summaries
            if item.get("object_id") is not None
        }
        normalized: list[dict[str, Any]] = []
        for index, object_id in enumerate(candidate_ids):
            summary = dict(summary_map.get(object_id, {"object_id": object_id}))
            if index < len(candidate_scores):
                summary.setdefault("score", candidate_scores[index])
            normalized.append(summary)
        return normalized

    @staticmethod
    def _selected_summaries(
        primary_objects: list[Any],
        selected_object_ids: list[str],
    ) -> list[dict[str, Any]]:
        object_map = {obj.id: obj for obj in primary_objects}
        summaries: list[dict[str, Any]] = []
        for object_id in selected_object_ids:
            obj = object_map.get(object_id)
            if obj is None:
                summaries.append({"object_id": object_id})
                continue
            summaries.append(
                {
                    "object_id": obj.id,
                    "type": obj.type,
                    "status": obj.status,
                    "episode_id": obj.metadata.get("episode_id"),
                    "content_preview": _object_content_preview(obj.content),
                }
            )
        return summaries

    def _build_response(
        self,
        *,
        execution: _ModeExecution,
        request: AccessRunRequest,
        context: PrimitiveExecutionContext,
        trace: AccessRunTrace,
        candidate_ids: list[str] | None = None,
        candidate_summaries: list[dict[str, Any]] | None = None,
        read_object_ids: list[str] | None = None,
        expanded_object_ids: list[str] | None = None,
    ) -> AccessRunResponse:
        answer = self._answer(request=request, execution=execution, context=context)

        # β-S1: build evidence_summary from selected objects (top-3)
        evidence_summary = self._build_evidence_summary(execution)

        return AccessRunResponse(
            resolved_mode=execution.mode,
            context_kind=execution.context_kind,
            context_object_ids=list(execution.context_object_ids),
            context_text=execution.context_text,
            context_token_count=execution.context_token_count,
            candidate_ids=list(execution.candidate_ids if candidate_ids is None else candidate_ids),
            candidate_summaries=list(
                execution.candidate_summaries
                if candidate_summaries is None
                else candidate_summaries
            ),
            read_object_ids=list(
                execution.read_object_ids if read_object_ids is None else read_object_ids
            ),
            expanded_object_ids=list(
                execution.expanded_object_ids
                if expanded_object_ids is None
                else expanded_object_ids
            ),
            selected_object_ids=list(execution.selected_object_ids),
            selected_summaries=list(execution.selected_summaries),
            answer_text=answer["answer_text"],
            answer_support_ids=answer["answer_support_ids"],
            answer_trace=answer["answer_trace"],
            verification_notes=list(execution.verification_notes),
            trace=trace,
            evidence_summary=evidence_summary,
        )

    def _build_evidence_summary(
        self,
        execution: _ModeExecution,
    ) -> list[EvidenceSummaryItem]:
        """Build evidence summary items from selected objects (Phase β-S1)."""
        items: list[EvidenceSummaryItem] = []
        score_map: dict[str, float] = {}
        for summary in execution.candidate_summaries:
            if isinstance(summary, dict) and "object_id" in summary:
                score_map[summary["object_id"]] = float(summary.get("score", 0.0))

        for oid in execution.selected_object_ids[:3]:
            if not self.store.has_object(oid):
                continue
            obj = self.store.read_object(oid)
            content = obj.get("content", "")
            if isinstance(content, dict):
                brief = str(content)[:120]
            else:
                brief = str(content)[:120]
            if not brief:
                brief = str(oid)
            relevance = min(1.0, max(0.0, score_map.get(oid, 0.0)))
            items.append(
                EvidenceSummaryItem(
                    object_id=oid,
                    object_type=str(obj.get("type", "unknown")),
                    brief=brief,
                    relevance_score=round(relevance, 4),
                )
            )
        return items

    def _answer(
        self,
        *,
        request: AccessRunRequest,
        execution: _ModeExecution,
        context: PrimitiveExecutionContext,
    ) -> dict[str, Any]:
        draft_text = self._answer_draft_text(execution)
        if not draft_text:
            draft_text = execution.context_text
        provider_config = self._capability_provider_config(context)
        support_ids = self._answer_support_ids(execution)
        answer = self._capability_service.answer(
            CapabilityAnswerRequest(
                request_id=f"access-answer-{request.task_id}-{execution.mode.value}",
                question=_answer_question_text(request.query),
                context_text=draft_text,
                support_ids=support_ids,
                hard_constraints=list(request.hard_constraints),
                capture_raw_exchange=request.capture_raw_exchange,
            ),
            provider_config=provider_config,
        )
        return {
            "answer_text": answer.answer_text,
            "answer_support_ids": list(answer.support_ids),
            "answer_trace": answer.trace.model_dump(mode="json"),
        }

    @staticmethod
    def _answer_support_ids(execution: _ModeExecution) -> list[str]:
        if execution.context_kind is AccessContextKind.WORKSPACE:
            return list(execution.selected_object_ids)
        return list(execution.context_object_ids)

    def _answer_draft_text(self, execution: _ModeExecution) -> str:
        try:
            payload = json.loads(execution.context_text)
        except (TypeError, ValueError):
            return execution.context_text

        if execution.context_kind is AccessContextKind.RAW_TOPK:
            objects = payload.get("objects")
            if not isinstance(objects, list):
                return execution.context_text
            parts = [
                _support_text_for_object_payload(obj) for obj in objects if isinstance(obj, dict)
            ]
            return " | ".join(part for part in parts if part)

        slots = payload.get("slots")
        if not isinstance(slots, list):
            return execution.context_text
        parts = [
            str(slot.get("summary", "")).strip()
            for slot in slots
            if isinstance(slot, dict) and str(slot.get("summary", "")).strip()
        ]
        return " | ".join(parts)

    def _capability_provider_config(
        self,
        context: PrimitiveExecutionContext,
    ) -> Any:
        if not context.provider_selection:
            return None
        try:
            return resolve_capability_provider_config(
                selection=context.provider_selection,
                env=(
                    self._provider_env_resolver()
                    if self._provider_env_resolver is not None
                    else None
                ),
            )
        except RuntimeError as exc:
            raise AccessServiceError(str(exc)) from exc

    @staticmethod
    def _require_retrieve_success(
        result: PrimitiveExecutionResult,
    ) -> RetrieveResponse:
        response = _AccessOpsMixin._require_success_payload(result)
        return RetrieveResponse.model_validate(response)

    @staticmethod
    def _require_read_success(
        result: PrimitiveExecutionResult,
    ) -> ReadResponse:
        response = _AccessOpsMixin._require_success_payload(result)
        return ReadResponse.model_validate(response)

    @staticmethod
    def _require_success_payload(
        result: PrimitiveExecutionResult,
    ) -> dict[str, Any]:
        if result.outcome is not PrimitiveOutcome.SUCCESS or result.response is None:
            message = "runtime access primitive failed"
            if result.error is not None:
                message = f"{result.error.code.value}: {result.error.message}"
            raise AccessServiceError(message)
        return result.response


def _object_content_preview(content: Any) -> str | None:
    if content is None:
        return None
    if isinstance(content, dict):
        summary = content.get("summary")
        raw = summary if isinstance(summary, str) else str(content)
    elif isinstance(content, str):
        raw = content
    else:
        raw = str(content)
    compact = " ".join(raw.split())
    if not compact:
        return None
    return compact[:77] + "..." if len(compact) > 80 else compact

def _support_text_for_object_payload(obj: dict[str, Any]) -> str:
    content = obj.get("content")
    if isinstance(content, dict):
        for key in ("summary", "text", "result_summary"):
            value = content.get(key)
            if value is not None:
                return str(value)
    if content is not None:
        return json.dumps(content, ensure_ascii=True, sort_keys=True)
    return ""
