"""Audit helpers for Phase L telemetry completeness and replayability."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from .contracts import (
    TELEMETRY_COVERAGE_SURFACES,
    TelemetryEvent,
    TelemetryEventKind,
    TelemetryScope,
)


@dataclass(frozen=True)
class TelemetryCoverageScopeResult:
    scope: TelemetryScope
    event_count: int
    observed: bool


@dataclass(frozen=True)
class TelemetryCoverageAuditResult:
    expected_scope_count: int
    observed_scope_count: int
    missing_scopes: tuple[TelemetryScope, ...]
    scope_results: tuple[TelemetryCoverageScopeResult, ...]

    @property
    def coverage(self) -> float:
        if self.expected_scope_count == 0:
            return 1.0
        return round(self.observed_scope_count / float(self.expected_scope_count), 4)

    @property
    def passed(self) -> bool:
        return not self.missing_scopes


@dataclass(frozen=True)
class TelemetryDebugFieldRuleResult:
    rule_id: str
    matched_event_count: int
    complete_event_count: int
    incomplete_event_ids: tuple[str, ...]

    @property
    def coverage(self) -> float:
        if self.matched_event_count == 0:
            return 1.0
        return round(self.complete_event_count / float(self.matched_event_count), 4)


@dataclass(frozen=True)
class TelemetryDebugFieldAuditResult:
    audited_rule_count: int
    applicable_rule_count: int
    complete_event_count: int
    audited_event_count: int
    rule_results: tuple[TelemetryDebugFieldRuleResult, ...]

    @property
    def coverage(self) -> float:
        if self.audited_event_count == 0:
            return 1.0
        return round(self.complete_event_count / float(self.audited_event_count), 4)

    @property
    def passed(self) -> bool:
        return self.coverage >= 0.95


@dataclass(frozen=True)
class TelemetryTraceAuditEventResult:
    event_id: str
    run_id: str
    scope: TelemetryScope
    kind: TelemetryEventKind
    complete: bool
    missing_fields: tuple[str, ...]


@dataclass(frozen=True)
class TelemetryTraceAuditResult:
    audited_event_count: int
    complete_event_count: int
    missing_run_id_count: int
    missing_operation_id_count: int
    missing_job_id_count: int
    missing_workspace_id_count: int
    missing_object_version_count: int
    missing_parent_event_count: int
    out_of_order_parent_event_count: int
    event_results: tuple[TelemetryTraceAuditEventResult, ...]

    @property
    def coverage(self) -> float:
        if self.audited_event_count == 0:
            return 1.0
        return round(self.complete_event_count / float(self.audited_event_count), 4)

    @property
    def incomplete_event_count(self) -> int:
        return self.audited_event_count - self.complete_event_count

    @property
    def passed(self) -> bool:
        return self.incomplete_event_count == 0


@dataclass(frozen=True)
class TelemetryStateDeltaAuditResult:
    audited_event_count: int
    complete_event_count: int
    incomplete_event_ids: tuple[str, ...]

    @property
    def coverage(self) -> float:
        if self.audited_event_count == 0:
            return 1.0
        return round(self.complete_event_count / float(self.audited_event_count), 4)

    @property
    def passed(self) -> bool:
        return self.coverage >= 0.95


@dataclass(frozen=True)
class TelemetryTimelineRunResult:
    run_id: str
    event_count: int
    root_event_count: int
    duplicate_event_id_count: int
    missing_parent_event_count: int
    out_of_order_parent_event_count: int
    replayable: bool


@dataclass(frozen=True)
class TelemetryTimelineAuditResult:
    audited_run_count: int
    replayable_run_count: int
    run_results: tuple[TelemetryTimelineRunResult, ...]

    @property
    def replayable_ratio(self) -> float:
        if self.audited_run_count == 0:
            return 1.0
        return round(self.replayable_run_count / float(self.audited_run_count), 4)

    @property
    def passed(self) -> bool:
        return self.replayable_ratio >= 0.95


def evaluate_telemetry_coverage_audit(
    events: Sequence[TelemetryEvent] | Iterable[TelemetryEvent],
    *,
    expected_scopes: Sequence[TelemetryScope] = TELEMETRY_COVERAGE_SURFACES,
) -> TelemetryCoverageAuditResult:
    """Audit whether all required telemetry surfaces are represented."""

    event_list = tuple(events)
    counts: defaultdict[TelemetryScope, int] = defaultdict(int)
    for event in event_list:
        counts[event.scope] += 1
    scope_results = tuple(
        TelemetryCoverageScopeResult(
            scope=scope,
            event_count=counts[scope],
            observed=counts[scope] > 0,
        )
        for scope in expected_scopes
    )
    missing_scopes = tuple(result.scope for result in scope_results if not result.observed)
    return TelemetryCoverageAuditResult(
        expected_scope_count=len(expected_scopes),
        observed_scope_count=len(expected_scopes) - len(missing_scopes),
        missing_scopes=missing_scopes,
        scope_results=scope_results,
    )


def evaluate_telemetry_debug_field_audit(
    events: Sequence[TelemetryEvent] | Iterable[TelemetryEvent],
) -> TelemetryDebugFieldAuditResult:
    """Audit that key debug-facing event fields are present on critical events."""

    event_list = tuple(events)
    rule_results: list[TelemetryDebugFieldRuleResult] = []
    complete_event_count = 0
    audited_event_count = 0

    for rule in _debug_field_rules():
        matched_events = [event for event in event_list if rule.applies(event)]
        incomplete_event_ids = [
            event.event_id for event in matched_events if rule.missing_fields(event)
        ]
        matched_count = len(matched_events)
        complete_count = matched_count - len(incomplete_event_ids)
        complete_event_count += complete_count
        audited_event_count += matched_count
        rule_results.append(
            TelemetryDebugFieldRuleResult(
                rule_id=rule.rule_id,
                matched_event_count=matched_count,
                complete_event_count=complete_count,
                incomplete_event_ids=tuple(incomplete_event_ids),
            )
        )

    return TelemetryDebugFieldAuditResult(
        audited_rule_count=len(rule_results),
        applicable_rule_count=sum(result.matched_event_count > 0 for result in rule_results),
        complete_event_count=complete_event_count,
        audited_event_count=audited_event_count,
        rule_results=tuple(rule_results),
    )


def evaluate_telemetry_trace_audit(
    events: Sequence[TelemetryEvent] | Iterable[TelemetryEvent],
) -> TelemetryTraceAuditResult:
    """Audit correlation-chain completeness on a captured telemetry stream."""

    event_list = tuple(events)
    run_event_indexes = _run_event_indexes(event_list)
    event_results: list[TelemetryTraceAuditEventResult] = []

    missing_run_id_count = 0
    missing_operation_id_count = 0
    missing_job_id_count = 0
    missing_workspace_id_count = 0
    missing_object_version_count = 0
    missing_parent_event_count = 0
    out_of_order_parent_event_count = 0

    for index, event in enumerate(event_list):
        missing_fields: list[str] = []
        if not event.run_id:
            missing_fields.append("run_id")
            missing_run_id_count += 1
        if not event.operation_id:
            missing_fields.append("operation_id")
            missing_operation_id_count += 1
        if event.scope in {TelemetryScope.OFFLINE, TelemetryScope.GOVERNANCE} and not event.job_id:
            missing_fields.append("job_id")
            missing_job_id_count += 1
        if event.scope is TelemetryScope.WORKSPACE and not event.workspace_id:
            missing_fields.append("workspace_id")
            missing_workspace_id_count += 1
        if event.kind is TelemetryEventKind.STATE_DELTA and event.object_version is None:
            missing_fields.append("object_version")
            missing_object_version_count += 1
        if event.parent_event_id:
            parent_index = run_event_indexes[_run_key(event, index)].get(event.parent_event_id)
            if parent_index is None:
                missing_fields.append("parent_event_id")
                missing_parent_event_count += 1
            elif parent_index >= index:
                missing_fields.append("parent_event_order")
                out_of_order_parent_event_count += 1

        event_results.append(
            TelemetryTraceAuditEventResult(
                event_id=event.event_id,
                run_id=event.run_id,
                scope=event.scope,
                kind=event.kind,
                complete=not missing_fields,
                missing_fields=tuple(missing_fields),
            )
        )

    complete_event_count = sum(result.complete for result in event_results)
    return TelemetryTraceAuditResult(
        audited_event_count=len(event_list),
        complete_event_count=complete_event_count,
        missing_run_id_count=missing_run_id_count,
        missing_operation_id_count=missing_operation_id_count,
        missing_job_id_count=missing_job_id_count,
        missing_workspace_id_count=missing_workspace_id_count,
        missing_object_version_count=missing_object_version_count,
        missing_parent_event_count=missing_parent_event_count,
        out_of_order_parent_event_count=out_of_order_parent_event_count,
        event_results=tuple(event_results),
    )


def evaluate_telemetry_state_delta_audit(
    events: Sequence[TelemetryEvent] | Iterable[TelemetryEvent],
) -> TelemetryStateDeltaAuditResult:
    """Audit state-delta completeness for before/after/delta snapshots."""

    event_list = tuple(event for event in events if event.kind is TelemetryEventKind.STATE_DELTA)
    incomplete_event_ids: list[str] = []

    for event in event_list:
        if (
            event.before is None
            or event.after is None
            or event.delta is None
            or event.object_version is None
        ):
            incomplete_event_ids.append(event.event_id)

    return TelemetryStateDeltaAuditResult(
        audited_event_count=len(event_list),
        complete_event_count=len(event_list) - len(incomplete_event_ids),
        incomplete_event_ids=tuple(incomplete_event_ids),
    )


def evaluate_telemetry_timeline_audit(
    events: Sequence[TelemetryEvent] | Iterable[TelemetryEvent],
) -> TelemetryTimelineAuditResult:
    """Audit whether recorded runs can be replayed into ordered causal timelines."""

    event_list = tuple(events)
    runs = _group_events_by_run(event_list)
    run_results: list[TelemetryTimelineRunResult] = []

    for run_id, run_events in runs.items():
        id_counts: dict[str, int] = defaultdict(int)
        full_indexes = {event.event_id: index for index, event in enumerate(run_events)}
        root_event_count = 0
        missing_parent_event_count = 0
        out_of_order_parent_event_count = 0

        for index, event in enumerate(run_events):
            id_counts[event.event_id] += 1
            if event.parent_event_id is None:
                root_event_count += 1
                continue
            parent_index = full_indexes.get(event.parent_event_id)
            if parent_index is None:
                missing_parent_event_count += 1
            elif parent_index >= index:
                out_of_order_parent_event_count += 1

        duplicate_event_id_count = sum(count - 1 for count in id_counts.values() if count > 1)
        replayable = (
            root_event_count > 0
            and duplicate_event_id_count == 0
            and missing_parent_event_count == 0
            and out_of_order_parent_event_count == 0
        )
        run_results.append(
            TelemetryTimelineRunResult(
                run_id=run_id,
                event_count=len(run_events),
                root_event_count=root_event_count,
                duplicate_event_id_count=duplicate_event_id_count,
                missing_parent_event_count=missing_parent_event_count,
                out_of_order_parent_event_count=out_of_order_parent_event_count,
                replayable=replayable,
            )
        )

    replayable_run_count = sum(result.replayable for result in run_results)
    return TelemetryTimelineAuditResult(
        audited_run_count=len(run_results),
        replayable_run_count=replayable_run_count,
        run_results=tuple(run_results),
    )


def assert_telemetry_trace_audit(result: TelemetryTraceAuditResult) -> None:
    if result.passed:
        return
    raise RuntimeError(
        "L-3 failed: "
        f"complete={result.complete_event_count}/{result.audited_event_count}, "
        f"missing_run_id={result.missing_run_id_count}, "
        f"missing_operation_id={result.missing_operation_id_count}, "
        f"missing_job_id={result.missing_job_id_count}, "
        f"missing_workspace_id={result.missing_workspace_id_count}, "
        f"missing_object_version={result.missing_object_version_count}, "
        f"missing_parent={result.missing_parent_event_count}, "
        f"out_of_order_parent={result.out_of_order_parent_event_count}"
    )


def assert_telemetry_coverage_audit(result: TelemetryCoverageAuditResult) -> None:
    if result.passed:
        return
    raise RuntimeError(
        "L-1 failed: "
        f"observed_scopes={result.observed_scope_count}/{result.expected_scope_count}, "
        f"missing_scopes={[scope.value for scope in result.missing_scopes]}"
    )


def assert_telemetry_debug_field_audit(result: TelemetryDebugFieldAuditResult) -> None:
    if result.passed:
        return
    raise RuntimeError(
        "L-6 failed: "
        f"complete_debug_events={result.complete_event_count}/{result.audited_event_count}"
    )


def assert_telemetry_state_delta_audit(result: TelemetryStateDeltaAuditResult) -> None:
    if result.passed:
        return
    raise RuntimeError(
        "L-2 failed: "
        f"complete_state_delta={result.complete_event_count}/{result.audited_event_count}"
    )


def assert_telemetry_timeline_audit(result: TelemetryTimelineAuditResult) -> None:
    if result.passed:
        return
    raise RuntimeError(
        f"L-5 failed: replayable_runs={result.replayable_run_count}/{result.audited_run_count}"
    )


def _run_event_indexes(
    events: Sequence[TelemetryEvent],
) -> dict[str, dict[str, int]]:
    grouped: dict[str, dict[str, int]] = defaultdict(dict)
    for index, event in enumerate(events):
        grouped[_run_key(event, index)][event.event_id] = index
    return grouped


def _group_events_by_run(
    events: Sequence[TelemetryEvent],
) -> dict[str, list[TelemetryEvent]]:
    grouped: dict[str, list[TelemetryEvent]] = defaultdict(list)
    for index, event in enumerate(events):
        grouped[_run_key(event, index)].append(event)
    return grouped


def _run_key(event: TelemetryEvent, index: int) -> str:
    return event.run_id or f"missing-run-id-{index}"


@dataclass(frozen=True)
class _TelemetryDebugFieldRule:
    rule_id: str
    applies: Any
    missing_fields: Any


def _debug_field_rules() -> tuple[_TelemetryDebugFieldRule, ...]:
    return (
        _TelemetryDebugFieldRule(
            rule_id="primitive_budget_decision",
            applies=lambda event: (
                event.scope is TelemetryScope.PRIMITIVE
                and event.kind is TelemetryEventKind.DECISION
            ),
            missing_fields=lambda event: _missing_fields(
                event,
                payload_fields=("primitive", "outcome", "request"),
                debug_fields=("error_code",),
            ),
        ),
        _TelemetryDebugFieldRule(
            rule_id="retrieval_ranking",
            applies=lambda event: (
                event.scope is TelemetryScope.RETRIEVAL
                and event.kind is TelemetryEventKind.DECISION
            ),
            missing_fields=lambda event: _missing_fields(
                event,
                payload_fields=("retrieval_backend", "candidate_ids", "candidate_scores"),
                debug_fields=("returned_count", "used_vector_override"),
            ),
        ),
        _TelemetryDebugFieldRule(
            rule_id="workspace_selection",
            applies=lambda event: (
                event.scope is TelemetryScope.WORKSPACE
                and event.kind is TelemetryEventKind.DECISION
            ),
            missing_fields=lambda event: _missing_fields(
                event,
                payload_fields=("selected_ids", "skipped_ids", "ranked_candidates"),
                debug_fields=("selected_count", "skipped_count", "deduped_candidate_count"),
            ),
        ),
        _TelemetryDebugFieldRule(
            rule_id="access_mode_switch",
            applies=lambda event: (
                event.scope is TelemetryScope.ACCESS and event.kind is TelemetryEventKind.DECISION
            ),
            missing_fields=lambda event: _missing_fields(
                event,
                payload_fields=("mode", "reason_code", "switch_kind", "target_ids"),
                debug_fields=("summary",),
            ),
        ),
        _TelemetryDebugFieldRule(
            rule_id="governance_selection",
            applies=lambda event: (
                event.scope is TelemetryScope.GOVERNANCE
                and event.kind is TelemetryEventKind.DECISION
                and str(event.payload.get("stage", "")).endswith("_selection")
            ),
            missing_fields=lambda event: _missing_fields(
                event,
                payload_fields=("stage", "candidate_object_ids"),
                debug_fields=("candidate_object_count",),
            ),
        ),
    )


def _missing_fields(
    event: TelemetryEvent,
    *,
    payload_fields: Sequence[str] = (),
    debug_fields: Sequence[str] = (),
    any_debug_fields: Sequence[str] = (),
) -> tuple[str, ...]:
    missing: list[str] = []
    for field in payload_fields:
        if field not in event.payload:
            missing.append(f"payload.{field}")
    for field in debug_fields:
        if field not in event.debug_fields:
            missing.append(f"debug_fields.{field}")
    if any_debug_fields and not any(field in event.debug_fields for field in any_debug_fields):
        missing.extend(f"debug_fields.{field}" for field in any_debug_fields)
    return tuple(missing)
