"""Frontend-facing debug timeline projection helpers (moved to app layer)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from mind.app.contracts import (
    FrontendDebugContextView,
    FrontendDebugEvidenceView,
    FrontendDebugTimelineEvent,
    FrontendDebugTimelineQuery,
    FrontendDebugTimelineResponse,
    FrontendObjectDeltaView,
)
from mind.telemetry import TelemetryEvent, TelemetryEventKind, TelemetryScope


class FrontendDebugUnavailableError(RuntimeError):
    """Raised when frontend debug projection is requested outside dev-mode."""


def build_frontend_debug_timeline(
    events: Sequence[TelemetryEvent] | Iterable[TelemetryEvent],
    query: FrontendDebugTimelineQuery | dict[str, object],
    *,
    dev_mode: bool,
) -> FrontendDebugTimelineResponse:
    """Project raw telemetry into the stable frontend-facing debug contract."""

    if not dev_mode:
        raise FrontendDebugUnavailableError("frontend debug timeline requires dev_mode=true")

    validated_query = FrontendDebugTimelineQuery.model_validate(query)
    event_list = tuple(events)
    matched_events = tuple(event for event in event_list if _matches(event, validated_query))
    returned_events = matched_events[: validated_query.limit]
    selected_ids_by_operation = _selected_ids_by_operation(returned_events)

    timeline = [
        FrontendDebugTimelineEvent(
            event_id=event.event_id,
            parent_event_id=event.parent_event_id,
            occurred_at=event.occurred_at,
            scope=event.scope,
            kind=event.kind,
            run_id=event.run_id,
            operation_id=event.operation_id,
            job_id=event.job_id,
            workspace_id=event.workspace_id,
            object_id=event.object_id,
            object_version=event.object_version,
            label=_event_label(event),
            summary=_event_summary(event),
            payload=dict(event.payload) if validated_query.include_payload else None,
            debug_fields=dict(event.debug_fields) if validated_query.include_debug_fields else None,
        )
        for event in returned_events
    ]
    object_deltas = [
        FrontendObjectDeltaView(
            event_id=event.event_id,
            occurred_at=event.occurred_at,
            object_id=str(event.object_id),
            object_version=int(event.object_version),
            summary=_event_summary(event),
            before=dict(event.before or {}),
            after=dict(event.after or {}),
            delta=dict(event.delta or {}),
        )
        for event in returned_events
        if validated_query.include_state_deltas
        and event.kind is TelemetryEventKind.STATE_DELTA
        and event.object_id is not None
        and event.object_version is not None
    ]
    context_views = [
        FrontendDebugContextView(
            event_id=event.event_id,
            occurred_at=event.occurred_at,
            operation_id=event.operation_id,
            workspace_id=event.workspace_id,
            context_kind=str(event.payload.get("context_kind") or "unknown"),
            summary=_event_summary(event),
            candidate_ids=_as_str_list(event.payload.get("candidate_ids")),
            selected_object_ids=_as_str_list(event.payload.get("selected_object_ids")),
            context_object_ids=_as_str_list(event.payload.get("context_object_ids")),
            verification_notes=_as_str_list(event.payload.get("verification_notes")),
        )
        for event in returned_events
        if event.scope is TelemetryScope.ACCESS and event.kind is TelemetryEventKind.CONTEXT_RESULT
    ]
    evidence_views = [
        *_project_retrieval_evidence(returned_events, selected_ids_by_operation),
        *_project_workspace_evidence(returned_events),
    ]
    available_scopes = sorted(
        {event.scope for event in returned_events}, key=lambda item: item.value
    )
    return FrontendDebugTimelineResponse(
        query=validated_query,
        total_event_count=len(event_list),
        matched_event_count=len(matched_events),
        returned_event_count=len(returned_events),
        available_scopes=available_scopes,
        timeline=timeline,
        object_deltas=object_deltas,
        context_views=context_views,
        evidence_views=evidence_views,
    )


def _matches(event: TelemetryEvent, query: FrontendDebugTimelineQuery) -> bool:
    if query.run_id is not None and event.run_id != query.run_id:
        return False
    if query.operation_id is not None and event.operation_id != query.operation_id:
        return False
    if query.job_id is not None and event.job_id != query.job_id:
        return False
    if query.workspace_id is not None and event.workspace_id != query.workspace_id:
        return False
    if query.object_id is not None and event.object_id != query.object_id:
        return False
    if query.occurred_after is not None and event.occurred_at < query.occurred_after:
        return False
    if query.occurred_before is not None and event.occurred_at > query.occurred_before:
        return False
    if query.scopes and event.scope not in query.scopes:
        return False
    if query.event_kinds and event.kind not in query.event_kinds:
        return False
    return True


def _event_label(event: TelemetryEvent) -> str:
    if event.scope is TelemetryScope.OBJECT_DELTA:
        return "Object Delta"
    return (
        f"{event.scope.value.replace('_', ' ').title()}"
        f" {event.kind.value.replace('_', ' ').title()}"
    )


def _event_summary(event: TelemetryEvent) -> str:
    payload = event.payload
    if event.kind is TelemetryEventKind.STATE_DELTA:
        return f"{event.object_id} -> v{event.object_version}"

    explicit_summary = payload.get("summary")
    if isinstance(explicit_summary, str) and explicit_summary:
        return explicit_summary

    if event.scope is TelemetryScope.PRIMITIVE:
        primitive = payload.get("primitive")
        outcome = payload.get("outcome")
        if primitive and outcome:
            return f"{primitive} {outcome}"
        if primitive:
            return f"{primitive} {event.kind.value}"
    if event.scope is TelemetryScope.RETRIEVAL:
        backend = payload.get("retrieval_backend")
        candidate_ids = payload.get("candidate_ids")
        if backend and isinstance(candidate_ids, list):
            return f"{backend} ranked {len(candidate_ids)} candidates"
    if event.scope is TelemetryScope.WORKSPACE:
        selected_ids = payload.get("selected_ids")
        if isinstance(selected_ids, list):
            return f"selected {len(selected_ids)} objects"
    if event.scope is TelemetryScope.ACCESS:
        mode = payload.get("mode")
        reason_code = payload.get("reason_code")
        if mode and reason_code:
            return f"{mode} via {reason_code}"
    if event.scope is TelemetryScope.OFFLINE:
        job_kind = payload.get("job_kind")
        stage = payload.get("stage")
        outcome = payload.get("outcome")
        if job_kind and stage:
            return f"{job_kind} {stage}"
        if job_kind and outcome:
            return f"{job_kind} {outcome}"
    if event.scope is TelemetryScope.GOVERNANCE:
        stage = payload.get("stage")
        outcome = payload.get("outcome")
        if stage and outcome:
            return f"{stage} {outcome}"
        if stage:
            return str(stage)

    return f"{event.scope.value}:{event.kind.value}"


def _selected_ids_by_operation(events: Sequence[TelemetryEvent]) -> dict[str, set[str]]:
    selected: dict[str, set[str]] = {}
    for event in events:
        if event.scope is TelemetryScope.ACCESS and event.kind is TelemetryEventKind.CONTEXT_RESULT:
            selected.setdefault(event.operation_id, set()).update(
                _as_str_list(event.payload.get("selected_object_ids"))
            )
            continue
        if event.scope is not TelemetryScope.WORKSPACE:
            continue
        if event.kind is not TelemetryEventKind.CONTEXT_RESULT:
            continue
        workspace_object = event.payload.get("workspace_object")
        if not isinstance(workspace_object, dict):
            continue
        content = workspace_object.get("content")
        if isinstance(content, dict):
            selected.setdefault(event.operation_id, set()).update(
                _as_str_list(content.get("selected_object_ids"))
            )
    return selected


def _project_retrieval_evidence(
    events: Sequence[TelemetryEvent],
    selected_ids_by_operation: dict[str, set[str]],
) -> list[FrontendDebugEvidenceView]:
    projected: list[FrontendDebugEvidenceView] = []
    for event in events:
        if event.scope is not TelemetryScope.RETRIEVAL:
            continue
        if event.kind is not TelemetryEventKind.ACTION_RESULT:
            continue
        candidate_summaries = event.payload.get("candidate_summaries")
        if not isinstance(candidate_summaries, list):
            continue
        selected_ids = selected_ids_by_operation.get(event.operation_id, set())
        for raw_summary in candidate_summaries:
            if not isinstance(raw_summary, dict):
                continue
            object_id = str(raw_summary.get("object_id") or "")
            if not object_id:
                continue
            object_type = raw_summary.get("object_type") or raw_summary.get("type")
            content_preview = raw_summary.get("content_preview")
            projected.append(
                FrontendDebugEvidenceView(
                    event_id=event.event_id,
                    occurred_at=event.occurred_at,
                    operation_id=event.operation_id,
                    workspace_id=event.workspace_id,
                    object_id=object_id,
                    object_type=str(object_type) if object_type is not None else None,
                    summary=str(content_preview or object_type or object_id),
                    selected=object_id in selected_ids,
                    score=_float_or_none(raw_summary.get("score")),
                    content_preview=str(content_preview) if content_preview is not None else None,
                    evidence_refs=[],
                    source_refs=[],
                )
            )
    return projected


def _project_workspace_evidence(
    events: Sequence[TelemetryEvent],
) -> list[FrontendDebugEvidenceView]:
    projected: list[FrontendDebugEvidenceView] = []
    for event in events:
        if event.scope is not TelemetryScope.WORKSPACE:
            continue
        if event.kind is not TelemetryEventKind.CONTEXT_RESULT:
            continue
        workspace_object = event.payload.get("workspace_object")
        if not isinstance(workspace_object, dict):
            continue
        metadata = workspace_object.get("metadata")
        if not isinstance(metadata, dict):
            continue
        slots = metadata.get("slots")
        if not isinstance(slots, list):
            continue
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            expand_pointer = slot.get("expand_pointer")
            object_id = ""
            if isinstance(expand_pointer, dict):
                object_id = str(expand_pointer.get("object_id") or "")
            if not object_id:
                source_refs = _as_str_list(slot.get("source_refs"))
                object_id = source_refs[0] if source_refs else ""
            if not object_id:
                continue
            projected.append(
                FrontendDebugEvidenceView(
                    event_id=event.event_id,
                    occurred_at=event.occurred_at,
                    operation_id=event.operation_id,
                    workspace_id=event.workspace_id,
                    object_id=object_id,
                    object_type=None,
                    summary=str(slot.get("summary") or object_id),
                    selected=True,
                    score=None,
                    priority=_float_or_none(slot.get("priority")),
                    reason_selected=(
                        str(slot.get("reason_selected"))
                        if slot.get("reason_selected") is not None
                        else None
                    ),
                    content_preview=None,
                    evidence_refs=_as_str_list(slot.get("evidence_refs")),
                    source_refs=_as_str_list(slot.get("source_refs")),
                )
            )
    return projected


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _float_or_none(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None
