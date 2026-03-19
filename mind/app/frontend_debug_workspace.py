"""Frontend-facing debug workspace metadata projection helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import datetime

from mind.app.contracts import FrontendDebugFilterOption, FrontendDebugWorkspaceResult
from mind.app.frontend_debug import FrontendDebugUnavailableError
from mind.telemetry import TelemetryEvent, TelemetryEventKind, TelemetryScope


def build_frontend_debug_workspace(
    events: Sequence[TelemetryEvent] | Iterable[TelemetryEvent],
    *,
    dev_mode: bool,
) -> FrontendDebugWorkspaceResult:
    """Project telemetry into frontend filter metadata for the debug workspace."""

    if not dev_mode:
        raise FrontendDebugUnavailableError("frontend debug timeline requires dev_mode=true")

    event_list = tuple(events)
    occurred_values = tuple(event.occurred_at for event in event_list)
    default_run_id = event_list[-1].run_id if event_list else None
    return FrontendDebugWorkspaceResult(
        total_event_count=len(event_list),
        default_run_id=default_run_id,
        earliest_occurred_at=min(occurred_values, default=None),
        latest_occurred_at=max(occurred_values, default=None),
        run_options=_build_identity_options(event_list, lambda event: event.run_id),
        operation_options=_build_identity_options(event_list, lambda event: event.operation_id),
        object_options=_build_identity_options(
            event_list,
            lambda event: event.object_id,
        ),
        job_options=_build_identity_options(
            event_list,
            lambda event: event.job_id,
        ),
        workspace_options=_build_identity_options(
            event_list,
            lambda event: event.workspace_id,
        ),
        scope_options=_build_enum_options(
            event_list,
            lambda event: event.scope,
            TelemetryScope,
        ),
        event_kind_options=_build_enum_options(
            event_list,
            lambda event: event.kind,
            TelemetryEventKind,
        ),
    )


def _build_identity_options(
    events: Sequence[TelemetryEvent],
    selector: Callable[[TelemetryEvent], str | None],
) -> list[FrontendDebugFilterOption]:
    stats: dict[str, tuple[int, datetime]] = {}
    for event in events:
        value = selector(event)
        if value is None:
            continue
        count, latest = stats.get(value, (0, event.occurred_at))
        stats[value] = (
            count + 1,
            max(latest, event.occurred_at),
        )
    ordered = sorted(
        stats.items(),
        key=lambda item: (-item[1][1].timestamp(), item[0]),
    )
    return _build_filter_options(ordered)


def _build_enum_options(
    events: Sequence[TelemetryEvent],
    selector: Callable[[TelemetryEvent], TelemetryScope | TelemetryEventKind],
    enum_type: type[TelemetryScope] | type[TelemetryEventKind],
) -> list[FrontendDebugFilterOption]:
    grouped: dict[str, tuple[int, datetime | None]] = {
        enum_value.value: (0, None) for enum_value in enum_type
    }
    labels: dict[str, str] = {enum_value.value: enum_value.value for enum_value in enum_type}
    for event in events:
        enum_value = selector(event)
        key = enum_value.value
        count, latest = grouped[key]
        grouped[key] = (
            count + 1,
            event.occurred_at if latest is None else max(latest, event.occurred_at),
        )
    return _build_filter_options(grouped.items(), labels=labels)


def _build_filter_options(
    grouped: Iterable[tuple[str, tuple[int, datetime | None]]],
    *,
    labels: dict[str, str] | None = None,
) -> list[FrontendDebugFilterOption]:
    resolved_labels = labels or {}
    return [
        FrontendDebugFilterOption(
            value=value,
            label=resolved_labels.get(value, value),
            event_count=count,
            latest_occurred_at=latest,
        )
        for value, (count, latest) in grouped
    ]
