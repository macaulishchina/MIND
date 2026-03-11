"""Runtime access execution service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from mind.kernel.store import MemoryStore, StoreError
from mind.primitives.contracts import (
    PrimitiveExecutionContext,
    PrimitiveExecutionResult,
    PrimitiveOutcome,
    ReadResponse,
    RetrieveResponse,
)
from mind.primitives.service import PrimitiveService, QueryEmbedder, VectorRetriever
from mind.telemetry import TelemetryEvent, TelemetryEventKind, TelemetryRecorder, TelemetryScope
from mind.workspace import (
    WorkspaceBuilder,
    WorkspaceBuildError,
    build_raw_topk_context,
    build_workspace_context,
)

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
)


class AccessServiceError(RuntimeError):
    """Raised when a runtime access execution cannot complete safely."""


@dataclass(frozen=True)
class _ModePlan:
    retrieve_limit: int
    primary_read_limit: int
    raw_context_limit: int
    workspace_slot_limit: int
    expanded_read_limit: int
    verification_read_limit: int
    purpose: str
    build_workspace: bool
    verify: bool


@dataclass(frozen=True)
class _ModeExecution:
    mode: AccessMode
    context_kind: AccessContextKind
    workspace_id: str | None
    context_object_ids: tuple[str, ...]
    context_text: str
    context_token_count: int
    candidate_ids: tuple[str, ...]
    candidate_summaries: tuple[dict[str, Any], ...]
    read_object_ids: tuple[str, ...]
    expanded_object_ids: tuple[str, ...]
    selected_object_ids: tuple[str, ...]
    selected_summaries: tuple[dict[str, Any], ...]
    verification_notes: tuple[str, ...]
    events: tuple[AccessModeTraceEvent, ...]
    has_reflection_signal: bool
    simple_enough: bool


_MODE_PLANS = {
    AccessMode.FLASH: _ModePlan(
        retrieve_limit=3,
        primary_read_limit=1,
        raw_context_limit=1,
        workspace_slot_limit=0,
        expanded_read_limit=0,
        verification_read_limit=0,
        purpose="flash access",
        build_workspace=False,
        verify=False,
    ),
    AccessMode.RECALL: _ModePlan(
        retrieve_limit=8,
        primary_read_limit=4,
        raw_context_limit=0,
        workspace_slot_limit=4,
        expanded_read_limit=0,
        verification_read_limit=0,
        purpose="recall workspace",
        build_workspace=True,
        verify=False,
    ),
    AccessMode.RECONSTRUCT: _ModePlan(
        retrieve_limit=12,
        primary_read_limit=6,
        raw_context_limit=0,
        workspace_slot_limit=6,
        expanded_read_limit=6,
        verification_read_limit=0,
        purpose="reconstruct workspace",
        build_workspace=True,
        verify=False,
    ),
    AccessMode.REFLECTIVE_ACCESS: _ModePlan(
        retrieve_limit=12,
        primary_read_limit=6,
        raw_context_limit=0,
        workspace_slot_limit=6,
        expanded_read_limit=6,
        verification_read_limit=6,
        purpose="reflective workspace",
        build_workspace=True,
        verify=True,
    ),
}


class AccessService:
    """Library-first surface for fixed and auto runtime access modes."""

    def __init__(
        self,
        store: MemoryStore,
        *,
        clock: Callable[[], datetime] | None = None,
        vector_retriever: VectorRetriever | None = None,
        query_embedder: QueryEmbedder | None = None,
        telemetry_recorder: TelemetryRecorder | None = None,
    ) -> None:
        self.store = store
        self._clock = clock or _utc_now
        self._telemetry_recorder = telemetry_recorder
        self._primitive_service = PrimitiveService(
            store,
            clock=self._clock,
            vector_retriever=vector_retriever,
            query_embedder=query_embedder,
            telemetry_recorder=telemetry_recorder,
        )
        self._workspace_builder = WorkspaceBuilder(
            store,
            clock=self._clock,
            telemetry_recorder=telemetry_recorder,
        )

    def run(
        self,
        request: AccessRunRequest | dict[str, Any],
        context: PrimitiveExecutionContext | dict[str, Any],
    ) -> AccessRunResponse:
        try:
            validated_request = AccessRunRequest.model_validate(request)
            execution_context = PrimitiveExecutionContext.model_validate(context)
        except ValidationError as exc:
            raise AccessServiceError(str(exc)) from exc

        run_id = execution_context.telemetry_run_id or f"access-{validated_request.task_id}"
        operation_id = f"access-{validated_request.task_id}"
        correlated_context = self._with_telemetry_context(
            execution_context,
            operation_id=operation_id,
            parent_event_id=f"{operation_id}-entry",
        )
        self._record_access_telemetry(
            enabled=execution_context.dev_mode,
            event=TelemetryEvent(
                event_id=f"{operation_id}-entry",
                scope=TelemetryScope.ACCESS,
                kind=TelemetryEventKind.ENTRY,
                occurred_at=self._clock(),
                run_id=run_id,
                operation_id=operation_id,
                actor=execution_context.actor,
                payload={
                    "requested_mode": validated_request.requested_mode.value,
                    "task_id": validated_request.task_id,
                    "task_family": (
                        validated_request.task_family.value
                        if validated_request.task_family is not None
                        else None
                    ),
                    "query_modes": [mode.value for mode in validated_request.query_modes],
                    "filters": validated_request.filters.model_dump(mode="json"),
                    "hard_constraints": list(validated_request.hard_constraints),
                },
                debug_fields={
                    "time_budget_ms": validated_request.time_budget_ms,
                },
            ),
        )

        if validated_request.requested_mode is AccessMode.AUTO:
            response = self._run_auto(validated_request, correlated_context)
        else:
            response = self._run_locked(validated_request, correlated_context)

        self._record_access_trace(
            response=response,
            actor=execution_context.actor,
            enabled=execution_context.dev_mode,
            run_id=run_id,
            operation_id=operation_id,
        )
        return response

    def _run_locked(
        self,
        request: AccessRunRequest,
        context: PrimitiveExecutionContext,
    ) -> AccessRunResponse:
        execution = self._execute_mode(request.requested_mode, request, context)
        events = [
            self._select_event(
                mode=request.requested_mode,
                reason_code=AccessReasonCode.EXPLICIT_MODE_REQUEST,
                switch_kind=AccessSwitchKind.INITIAL,
                summary=(
                    f"fixed mode {request.requested_mode.value} selected "
                    f"for task {request.task_id}"
                ),
            ),
            *execution.events,
            self._mode_summary_event(
                mode=execution.mode,
                candidate_ids=execution.candidate_ids,
                read_object_ids=execution.read_object_ids,
                context_object_ids=execution.context_object_ids,
            ),
        ]
        trace = AccessRunTrace(
            requested_mode=request.requested_mode,
            resolved_mode=execution.mode,
            task_family=request.task_family,
            time_budget_ms=request.time_budget_ms,
            hard_constraints=request.hard_constraints,
            events=events,
        )
        return self._build_response(execution=execution, trace=trace)

    def _run_auto(
        self,
        request: AccessRunRequest,
        context: PrimitiveExecutionContext,
    ) -> AccessRunResponse:
        initial_mode, initial_reason = self._choose_initial_auto_mode(request)
        events = [
            self._select_event(
                mode=initial_mode,
                reason_code=initial_reason,
                switch_kind=AccessSwitchKind.INITIAL,
                summary=f"auto selected {initial_mode.value} for task {request.task_id}",
            )
        ]

        first_execution = self._execute_mode(initial_mode, request, context)
        events.extend(first_execution.events)
        aggregate_candidate_ids = list(first_execution.candidate_ids)
        aggregate_candidate_summaries = list(first_execution.candidate_summaries)
        aggregate_read_object_ids = list(first_execution.read_object_ids)
        aggregate_expanded_object_ids = list(first_execution.expanded_object_ids)
        final_execution = first_execution

        switch = self._choose_auto_switch(request, first_execution)
        if switch is not None:
            target_mode, reason_code, switch_kind = switch
            events.append(
                self._select_event(
                    mode=target_mode,
                    reason_code=reason_code,
                    switch_kind=switch_kind,
                    from_mode=first_execution.mode,
                    summary=(
                        f"auto switched from {first_execution.mode.value} "
                        f"to {target_mode.value}"
                    ),
                )
            )
            final_execution = self._execute_mode(target_mode, request, context)
            events.extend(final_execution.events)
            aggregate_candidate_ids = _merge_ids(
                aggregate_candidate_ids,
                final_execution.candidate_ids,
            )
            aggregate_candidate_summaries = _merge_summaries(
                aggregate_candidate_summaries,
                final_execution.candidate_summaries,
            )
            aggregate_read_object_ids = _merge_ids(
                aggregate_read_object_ids,
                final_execution.read_object_ids,
            )
            aggregate_expanded_object_ids = _merge_ids(
                aggregate_expanded_object_ids,
                final_execution.expanded_object_ids,
            )

        events.append(
            self._mode_summary_event(
                mode=final_execution.mode,
                candidate_ids=tuple(aggregate_candidate_ids),
                read_object_ids=tuple(aggregate_read_object_ids),
                context_object_ids=final_execution.context_object_ids,
            )
        )
        trace = AccessRunTrace(
            requested_mode=AccessMode.AUTO,
            resolved_mode=final_execution.mode,
            task_family=request.task_family,
            time_budget_ms=request.time_budget_ms,
            hard_constraints=request.hard_constraints,
            events=events,
        )
        return self._build_response(
            execution=final_execution,
            trace=trace,
            candidate_ids=aggregate_candidate_ids,
            candidate_summaries=aggregate_candidate_summaries,
            read_object_ids=aggregate_read_object_ids,
            expanded_object_ids=aggregate_expanded_object_ids,
        )

    def _execute_mode(
        self,
        mode: AccessMode,
        request: AccessRunRequest,
        context: PrimitiveExecutionContext,
    ) -> _ModeExecution:
        plan = _MODE_PLANS[mode]
        retrieve_response = self._retrieve(request, context, plan)
        candidate_ids, candidate_scores = self._enrich_candidates(
            mode=mode,
            request=request,
            candidate_ids=list(retrieve_response.candidate_ids),
            candidate_scores=list(retrieve_response.scores),
        )
        candidate_summaries = self._candidate_summaries(
            list(retrieve_response.candidate_summaries),
            candidate_ids,
            candidate_scores,
        )
        if not candidate_ids:
            raise AccessServiceError("retrieve returned no candidates for runtime access")

        events = [
            AccessModeTraceEvent(
                event_kind=AccessTraceKind.RETRIEVE,
                mode=mode,
                summary=(
                    f"retrieved {len(candidate_ids)} candidates via "
                    f"{','.join(item.value for item in request.query_modes)}"
                ),
                target_ids=candidate_ids,
            )
        ]

        primary_read_ids = candidate_ids[: plan.primary_read_limit]
        primary_objects = self._read_objects(primary_read_ids, context)
        read_object_ids = list(primary_read_ids)
        expanded_object_ids: list[str] = []
        events.append(
            AccessModeTraceEvent(
                event_kind=AccessTraceKind.READ,
                mode=mode,
                summary=f"read {len(primary_read_ids)} primary objects",
                target_ids=primary_read_ids,
            )
        )

        if plan.expanded_read_limit > 0:
            expanded_object_ids = self._expand_source_refs(
                primary_objects,
                limit=plan.expanded_read_limit,
                exclude_ids=set(read_object_ids),
            )
            if expanded_object_ids:
                expanded_objects = self._read_objects(expanded_object_ids, context)
                primary_objects.extend(expanded_objects)
                read_object_ids.extend(expanded_object_ids)
                events.append(
                    AccessModeTraceEvent(
                        event_kind=AccessTraceKind.READ,
                        mode=mode,
                        summary=f"expanded {len(expanded_object_ids)} supporting objects",
                        target_ids=expanded_object_ids,
                    )
                )

        verification_notes: list[str] = []
        selected_object_ids: list[str] = []
        selected_summaries: list[dict[str, Any]] = []
        observed_objects = list(primary_objects)
        if not plan.build_workspace:
            context_object_ids = tuple(read_object_ids[: plan.raw_context_limit])
            serialized_context = build_raw_topk_context(self.store, context_object_ids)
            context_kind = AccessContextKind.RAW_TOPK
        else:
            workspace_candidate_ids = read_object_ids
            workspace_scores = self._workspace_scores(
                workspace_candidate_ids=workspace_candidate_ids,
                candidate_ids=candidate_ids,
                candidate_scores=candidate_scores,
            )
            try:
                workspace_result = self._workspace_builder.build(
                    task_id=request.task_id,
                    candidate_ids=workspace_candidate_ids,
                    candidate_scores=workspace_scores,
                    slot_limit=plan.workspace_slot_limit,
                    purpose=plan.purpose,
                    workspace_id=f"workspace-{mode.value}-{request.task_id}",
                    dev_mode=context.dev_mode,
                    telemetry_run_id=context.telemetry_run_id,
                    telemetry_operation_id=f"workspace-{mode.value}-{request.task_id}",
                    telemetry_parent_event_id=context.telemetry_parent_event_id,
                )
            except WorkspaceBuildError as exc:
                raise AccessServiceError(str(exc)) from exc
            serialized_context = build_workspace_context(workspace_result.workspace)
            context_kind = AccessContextKind.WORKSPACE
            selected_object_ids = list(workspace_result.selected_ids)
            selected_summaries = self._selected_summaries(primary_objects, selected_object_ids)
            events.append(
                AccessModeTraceEvent(
                    event_kind=AccessTraceKind.WORKSPACE,
                    mode=mode,
                    summary=(
                        f"built workspace with {len(selected_object_ids)} selected objects"
                    ),
                    target_ids=selected_object_ids,
                )
            )

            if plan.verify:
                verification_ids = self._expand_source_refs(
                    [obj for obj in primary_objects if obj.id in selected_object_ids],
                    limit=plan.verification_read_limit,
                    exclude_ids=set(read_object_ids),
                )
                verification_objects = self._read_objects(verification_ids, context)
                if verification_ids:
                    read_object_ids.extend(verification_ids)
                observed_objects.extend(verification_objects)
                verification_notes = self._verification_notes(
                    selected_objects=[
                        obj for obj in primary_objects if obj.id in selected_object_ids
                    ],
                    verification_objects=verification_objects,
                )
                events.append(
                    AccessModeTraceEvent(
                        event_kind=AccessTraceKind.VERIFY,
                        mode=mode,
                        summary=(
                            f"verified {len(selected_object_ids)} selected objects "
                            f"with {len(verification_notes)} checks"
                        ),
                        target_ids=verification_ids or selected_object_ids,
                    )
                )

            context_object_ids = tuple(serialized_context.object_ids)

        has_reflection_signal = self._has_reflection_signal(observed_objects, request.query)
        simple_enough = (
            len(candidate_ids) <= 2
            and not expanded_object_ids
            and (
                context_kind is AccessContextKind.RAW_TOPK
                or len(selected_object_ids) <= 1
            )
        )
        return _ModeExecution(
            mode=mode,
            context_kind=context_kind,
            workspace_id=(
                f"workspace-{mode.value}-{request.task_id}"
                if plan.build_workspace
                else None
            ),
            context_object_ids=context_object_ids,
            context_text=serialized_context.text,
            context_token_count=serialized_context.token_count,
            candidate_ids=tuple(candidate_ids),
            candidate_summaries=tuple(candidate_summaries),
            read_object_ids=tuple(read_object_ids),
            expanded_object_ids=tuple(expanded_object_ids),
            selected_object_ids=tuple(selected_object_ids),
            selected_summaries=tuple(selected_summaries),
            verification_notes=tuple(verification_notes),
            events=tuple(events),
            has_reflection_signal=has_reflection_signal,
            simple_enough=simple_enough,
        )

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
            event for event in response.trace.events if event.event_kind is AccessTraceKind.SELECT_MODE
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
                },
                debug_fields={
                    "trace_event_count": len(response.trace.events),
                    "expanded_read_count": len(response.expanded_object_ids),
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
    ) -> tuple[AccessMode, AccessReasonCode]:
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
        episode_raw_ids = {
            str(obj["id"]) for obj in self.store.raw_records_for_episode(episode_id)
        }
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
            object_id: candidate_scores[index]
            for index, object_id in enumerate(candidate_ids)
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
        trace: AccessRunTrace,
        candidate_ids: list[str] | None = None,
        candidate_summaries: list[dict[str, Any]] | None = None,
        read_object_ids: list[str] | None = None,
        expanded_object_ids: list[str] | None = None,
    ) -> AccessRunResponse:
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
            verification_notes=list(execution.verification_notes),
            trace=trace,
        )

    @staticmethod
    def _require_retrieve_success(
        result: PrimitiveExecutionResult,
    ) -> RetrieveResponse:
        response = AccessService._require_success_payload(result)
        return RetrieveResponse.model_validate(response)

    @staticmethod
    def _require_read_success(
        result: PrimitiveExecutionResult,
    ) -> ReadResponse:
        response = AccessService._require_success_payload(result)
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


def _merge_ids(existing: list[str], incoming: tuple[str, ...]) -> list[str]:
    merged = list(existing)
    for object_id in incoming:
        if object_id not in merged:
            merged.append(object_id)
    return merged


def _merge_summaries(
    existing: list[dict[str, Any]],
    incoming: tuple[dict[str, Any], ...],
) -> list[dict[str, Any]]:
    merged = list(existing)
    seen = {
        str(item.get("object_id"))
        for item in existing
        if item.get("object_id") is not None
    }
    for item in incoming:
        object_id = item.get("object_id")
        if object_id is None or str(object_id) in seen:
            continue
        merged.append(dict(item))
        seen.add(str(object_id))
    return merged


def _object_content_preview(content: Any) -> str | None:
    if content is None:
        return None
    if isinstance(content, str):
        compact = " ".join(content.split())
    elif isinstance(content, dict):
        summary = content.get("summary")
        if isinstance(summary, str):
            compact = " ".join(summary.split())
        else:
            compact = " ".join(str(content).split())
    else:
        compact = " ".join(str(content).split())
    if not compact:
        return None
    return compact[:77] + "..." if len(compact) > 80 else compact


def _query_text(query: str | dict[str, Any]) -> str:
    if isinstance(query, str):
        return query.lower()
    parts: list[str] = []
    for value in query.values():
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts).lower()


def _anchor_priority(object_type: str) -> int:
    if object_type == "SummaryNote":
        return 3
    if object_type == "TaskEpisode":
        return 2
    if object_type == "ReflectionNote":
        return 1
    return 0


def _constraints_require_deeper_context(hard_constraints: list[str]) -> bool:
    return any(
        marker in constraint
        for constraint in hard_constraints
        for marker in (
            "latest episode summary",
            "tool usage when present",
            "failure or revalidation signal",
        )
    )


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)
