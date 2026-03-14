"""Runtime access execution service."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from mind.capabilities import (
    CapabilityService,
)
from mind.kernel.store import MemoryStore
from mind.primitives.contracts import (
    PrimitiveExecutionContext,
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
    AccessTraceKind,
)

type ProviderEnvResolver = Callable[[], Mapping[str, str] | None]


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


def _access_action_summary(resolved_mode: str, answer_text: str | None) -> str:
    if not answer_text:
        return f"{resolved_mode} access completed"
    compact = " ".join(answer_text.split())
    excerpt = compact[:69] + "..." if len(compact) > 72 else compact
    return f"{resolved_mode} answer: {excerpt}"


def _answer_question_text(query: str | dict[str, Any]) -> str:
    if isinstance(query, str):
        return query
    return json.dumps(query, ensure_ascii=True, sort_keys=True)


def _query_text(query: str | dict[str, Any]) -> str:
    if isinstance(query, str):
        return query.lower()
    parts: list[str] = []
    for value in query.values():
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts).lower()


def _anchor_priority(object_type: str) -> int:
    return {"SummaryNote": 3, "TaskEpisode": 2, "ReflectionNote": 1}.get(object_type, 0)


def _constraints_require_deeper_context(hard_constraints: list[str]) -> bool:
    _MARKERS = (
        "latest episode summary",
        "tool usage when present",
        "failure or revalidation signal",
    )
    return any(m in c for c in hard_constraints for m in _MARKERS)


from .ops_mixin import _AccessOpsMixin  # noqa: E402, I001


class AccessService(_AccessOpsMixin):
    """Library-first surface for fixed and auto runtime access modes."""

    def __init__(
        self,
        store: MemoryStore,
        *,
        clock: Callable[[], datetime] | None = None,
        vector_retriever: VectorRetriever | None = None,
        query_embedder: QueryEmbedder | None = None,
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
            vector_retriever=vector_retriever,
            query_embedder=query_embedder,
            telemetry_recorder=telemetry_recorder,
            provider_env_resolver=provider_env_resolver,
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
                    f"fixed mode {request.requested_mode.value} selected for task {request.task_id}"
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
        return self._build_response(
            execution=execution,
            request=request,
            context=context,
            trace=trace,
        )

    def _run_auto(
        self,
        request: AccessRunRequest,
        context: PrimitiveExecutionContext,
    ) -> AccessRunResponse:
        # β-5.1: lightweight scouting retrieval (store-level, no budget cost)
        try:
            from mind.kernel.retrieval import keyword_score

            scout_scored: list[tuple[str, float]] = []
            for obj in self.store.iter_latest_objects(statuses=("active",)):
                ks = keyword_score(request.query, obj)
                if ks > 0:
                    scout_scored.append((str(obj["id"]), ks))
            scout_scored.sort(key=lambda t: t[1], reverse=True)
            scout_ids = [sid for sid, _ in scout_scored[:3]]
        except Exception:
            scout_ids = []

        initial_mode, initial_reason = self._choose_initial_auto_mode(
            request,
            scout_ids=scout_ids,
        )
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
                        f"auto switched from {first_execution.mode.value} to {target_mode.value}"
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
            request=request,
            context=context,
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

        # Phase γ-2: Graph-augmented retrieval — expand candidate set via
        # LinkEdge adjacency.  RECALL gets 1-hop, RECONSTRUCT / REFLECTIVE_ACCESS
        # get 2-hop expansion.
        graph_hops = _graph_hops_for_mode(mode)
        if graph_hops > 0 and candidate_ids:
            candidate_ids, candidate_scores = self._graph_expand(
                candidate_ids=candidate_ids,
                candidate_scores=candidate_scores,
                hops=graph_hops,
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

        # γ-4.3: tree-guided retrieval — when ArtifactIndex objects are among
        # candidates, drill down into their child sections for richer context.
        if plan.expanded_read_limit > 0:
            artifact_children = self._expand_artifact_index(
                primary_objects,
                limit=plan.expanded_read_limit,
                exclude_ids=set(read_object_ids) | set(expanded_object_ids),
            )
            if artifact_children:
                artifact_objects = self._read_objects(artifact_children, context)
                primary_objects.extend(artifact_objects)
                expanded_object_ids.extend(artifact_children)
                read_object_ids.extend(artifact_children)
                events.append(
                    AccessModeTraceEvent(
                        event_kind=AccessTraceKind.READ,
                        mode=mode,
                        summary=f"expanded {len(artifact_children)} ArtifactIndex children",
                        target_ids=artifact_children,
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
                    summary=(f"built workspace with {len(selected_object_ids)} selected objects"),
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
            and (context_kind is AccessContextKind.RAW_TOPK or len(selected_object_ids) <= 1)
        )
        return _ModeExecution(
            mode=mode,
            context_kind=context_kind,
            workspace_id=(
                f"workspace-{mode.value}-{request.task_id}" if plan.build_workspace else None
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
    seen = {str(item.get("object_id")) for item in existing if item.get("object_id") is not None}
    for item in incoming:
        object_id = item.get("object_id")
        if object_id is None or str(object_id) in seen:
            continue
        merged.append(dict(item))
        seen.add(str(object_id))
    return merged

def _graph_hops_for_mode(mode: AccessMode) -> int:
    """Return the number of graph hops to perform for a given access mode.

    FLASH — no expansion (latency sensitive).
    RECALL — 1-hop expansion to surface direct neighbours.
    RECONSTRUCT / REFLECTIVE_ACCESS — 2-hop expansion for richer context.
    """
    if mode is AccessMode.FLASH:
        return 0
    if mode is AccessMode.RECALL:
        return 1
    return 2


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)
