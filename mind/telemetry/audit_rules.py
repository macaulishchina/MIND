"""Debug field rules for telemetry audit completeness checks."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .contracts import (
    TelemetryEvent,
    TelemetryEventKind,
    TelemetryScope,
)


@dataclass(frozen=True)
class TelemetryDebugFieldRule:
    rule_id: str
    applies: Any
    missing_fields: Any


def debug_field_rules() -> tuple[TelemetryDebugFieldRule, ...]:
    return (
        TelemetryDebugFieldRule(
            rule_id="primitive_budget_decision",
            applies=lambda event: (
                event.scope is TelemetryScope.PRIMITIVE
                and event.kind is TelemetryEventKind.DECISION
            ),
            missing_fields=lambda event: missing_fields(
                event,
                payload_fields=("primitive", "outcome", "request"),
                debug_fields=("error_code",),
            ),
        ),
        TelemetryDebugFieldRule(
            rule_id="retrieval_ranking",
            applies=lambda event: (
                event.scope is TelemetryScope.RETRIEVAL
                and event.kind is TelemetryEventKind.DECISION
            ),
            missing_fields=lambda event: missing_fields(
                event,
                payload_fields=("retrieval_backend", "candidate_ids", "candidate_scores"),
                debug_fields=("returned_count", "used_vector_override"),
            ),
        ),
        TelemetryDebugFieldRule(
            rule_id="workspace_selection",
            applies=lambda event: (
                event.scope is TelemetryScope.WORKSPACE
                and event.kind is TelemetryEventKind.DECISION
            ),
            missing_fields=lambda event: missing_fields(
                event,
                payload_fields=("selected_ids", "skipped_ids", "ranked_candidates"),
                debug_fields=("selected_count", "skipped_count", "deduped_candidate_count"),
            ),
        ),
        TelemetryDebugFieldRule(
            rule_id="access_mode_switch",
            applies=lambda event: (
                event.scope is TelemetryScope.ACCESS and event.kind is TelemetryEventKind.DECISION
            ),
            missing_fields=lambda event: missing_fields(
                event,
                payload_fields=("mode", "reason_code", "switch_kind", "target_ids"),
                debug_fields=("summary",),
            ),
        ),
        TelemetryDebugFieldRule(
            rule_id="governance_selection",
            applies=lambda event: (
                event.scope is TelemetryScope.GOVERNANCE
                and event.kind is TelemetryEventKind.DECISION
                and str(event.payload.get("stage", "")).endswith("_selection")
            ),
            missing_fields=lambda event: missing_fields(
                event,
                payload_fields=("stage", "candidate_object_ids"),
                debug_fields=("candidate_object_count",),
            ),
        ),
    )


def missing_fields(
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
