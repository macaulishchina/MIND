"""Frozen fixture manifest for Phase L internal telemetry coverage."""

from __future__ import annotations

from dataclasses import dataclass

from mind.telemetry import TelemetryEventKind, TelemetryScope


@dataclass(frozen=True)
class InternalTelemetryScenario:
    scenario_id: str
    scope: TelemetryScope
    kind: TelemetryEventKind
    summary: str
    requires_state_delta: bool


def build_internal_telemetry_bench_v1() -> list[InternalTelemetryScenario]:
    """Return the frozen InternalTelemetryBench v1 skeleton."""

    scenarios = [
        InternalTelemetryScenario(
            "primitive_entry",
            TelemetryScope.PRIMITIVE,
            TelemetryEventKind.ENTRY,
            "Primitive entry event captures the incoming execution context.",
            False,
        ),
        InternalTelemetryScenario(
            "primitive_result",
            TelemetryScope.PRIMITIVE,
            TelemetryEventKind.ACTION_RESULT,
            "Primitive result event captures outcome, cost, and response shape.",
            False,
        ),
        InternalTelemetryScenario(
            "primitive_object_delta",
            TelemetryScope.PRIMITIVE,
            TelemetryEventKind.STATE_DELTA,
            "Primitive write records before/after/delta for the touched object.",
            True,
        ),
        InternalTelemetryScenario(
            "primitive_budget_decision",
            TelemetryScope.PRIMITIVE,
            TelemetryEventKind.DECISION,
            "Primitive budget rejection and approval paths emit explicit decisions.",
            False,
        ),
        InternalTelemetryScenario(
            "retrieval_entry",
            TelemetryScope.RETRIEVAL,
            TelemetryEventKind.ENTRY,
            "Retrieval entry records query mode, filters, and correlation ids.",
            False,
        ),
        InternalTelemetryScenario(
            "retrieval_ranking",
            TelemetryScope.RETRIEVAL,
            TelemetryEventKind.DECISION,
            "Retrieval ranking records candidate ordering and score metadata.",
            False,
        ),
        InternalTelemetryScenario(
            "retrieval_result",
            TelemetryScope.RETRIEVAL,
            TelemetryEventKind.ACTION_RESULT,
            "Retrieval result records selected candidates and recall surface.",
            False,
        ),
        InternalTelemetryScenario(
            "workspace_entry",
            TelemetryScope.WORKSPACE,
            TelemetryEventKind.ENTRY,
            "Workspace build entry records run and workspace ids.",
            False,
        ),
        InternalTelemetryScenario(
            "workspace_selection",
            TelemetryScope.WORKSPACE,
            TelemetryEventKind.DECISION,
            "Workspace selection records slot competition and chosen evidence.",
            False,
        ),
        InternalTelemetryScenario(
            "workspace_context_result",
            TelemetryScope.WORKSPACE,
            TelemetryEventKind.CONTEXT_RESULT,
            "Workspace result records final slots, token cost, and support shape.",
            False,
        ),
        InternalTelemetryScenario(
            "workspace_snapshot_delta",
            TelemetryScope.WORKSPACE,
            TelemetryEventKind.STATE_DELTA,
            "Workspace snapshot delta records context evolution across rebuilds.",
            True,
        ),
        InternalTelemetryScenario(
            "access_entry",
            TelemetryScope.ACCESS,
            TelemetryEventKind.ENTRY,
            "Access entry records requested mode, task family, and time budget.",
            False,
        ),
        InternalTelemetryScenario(
            "access_mode_switch",
            TelemetryScope.ACCESS,
            TelemetryEventKind.DECISION,
            "Access mode selection records upgrades, downgrades, and jumps.",
            False,
        ),
        InternalTelemetryScenario(
            "access_context_result",
            TelemetryScope.ACCESS,
            TelemetryEventKind.CONTEXT_RESULT,
            "Access result records candidate counts, selected ids, and context kind.",
            False,
        ),
        InternalTelemetryScenario(
            "access_answer_result",
            TelemetryScope.ACCESS,
            TelemetryEventKind.ACTION_RESULT,
            "Access answer generation records support ids and output quality fields.",
            False,
        ),
        InternalTelemetryScenario(
            "offline_job_entry",
            TelemetryScope.OFFLINE,
            TelemetryEventKind.ENTRY,
            "Offline job entry records worker, job kind, and correlation ids.",
            False,
        ),
        InternalTelemetryScenario(
            "offline_reflection_result",
            TelemetryScope.OFFLINE,
            TelemetryEventKind.ACTION_RESULT,
            "Offline reflection result records produced notes and evidence refs.",
            False,
        ),
        InternalTelemetryScenario(
            "offline_promotion_decision",
            TelemetryScope.OFFLINE,
            TelemetryEventKind.DECISION,
            "Offline promotion records selection and rejection reasons.",
            False,
        ),
        InternalTelemetryScenario(
            "offline_schema_delta",
            TelemetryScope.OFFLINE,
            TelemetryEventKind.STATE_DELTA,
            "Offline schema writes record before/after/delta for updated schema notes.",
            True,
        ),
        InternalTelemetryScenario(
            "governance_job_entry",
            TelemetryScope.GOVERNANCE,
            TelemetryEventKind.ENTRY,
            "Governance entry records actor, job id, and requested operation.",
            False,
        ),
        InternalTelemetryScenario(
            "governance_selection",
            TelemetryScope.GOVERNANCE,
            TelemetryEventKind.DECISION,
            "Governance selection records plan filters, visibility, and approval state.",
            False,
        ),
        InternalTelemetryScenario(
            "governance_execute_result",
            TelemetryScope.GOVERNANCE,
            TelemetryEventKind.ACTION_RESULT,
            "Governance execution result records affected objects and final outcome.",
            False,
        ),
        InternalTelemetryScenario(
            "governance_object_delta",
            TelemetryScope.GOVERNANCE,
            TelemetryEventKind.STATE_DELTA,
            "Governance mutations record before/after/delta for touched objects.",
            True,
        ),
        InternalTelemetryScenario(
            "object_delta_write_raw",
            TelemetryScope.OBJECT_DELTA,
            TelemetryEventKind.STATE_DELTA,
            "Object delta coverage includes new raw records.",
            True,
        ),
        InternalTelemetryScenario(
            "object_delta_summary_note",
            TelemetryScope.OBJECT_DELTA,
            TelemetryEventKind.STATE_DELTA,
            "Object delta coverage includes derived summary objects.",
            True,
        ),
        InternalTelemetryScenario(
            "object_delta_reflection_note",
            TelemetryScope.OBJECT_DELTA,
            TelemetryEventKind.STATE_DELTA,
            "Object delta coverage includes reflection objects.",
            True,
        ),
        InternalTelemetryScenario(
            "object_delta_schema_note",
            TelemetryScope.OBJECT_DELTA,
            TelemetryEventKind.STATE_DELTA,
            "Object delta coverage includes schema promotions.",
            True,
        ),
        InternalTelemetryScenario(
            "object_delta_archive",
            TelemetryScope.OBJECT_DELTA,
            TelemetryEventKind.STATE_DELTA,
            "Object delta coverage includes archive and deprecate mutations.",
            True,
        ),
        InternalTelemetryScenario(
            "cross_run_correlation",
            TelemetryScope.ACCESS,
            TelemetryEventKind.DECISION,
            "Correlation chain covers run_id, operation_id, workspace_id, and job_id handoff.",
            False,
        ),
        InternalTelemetryScenario(
            "timeline_replay_anchor",
            TelemetryScope.PRIMITIVE,
            TelemetryEventKind.ACTION_RESULT,
            "Timeline replay anchors preserve event ordering for mixed online/offline flows.",
            False,
        ),
    ]

    expected_scopes = {
        TelemetryScope.PRIMITIVE,
        TelemetryScope.RETRIEVAL,
        TelemetryScope.WORKSPACE,
        TelemetryScope.ACCESS,
        TelemetryScope.OFFLINE,
        TelemetryScope.GOVERNANCE,
        TelemetryScope.OBJECT_DELTA,
    }
    actual_scopes = {scenario.scope for scenario in scenarios}
    if actual_scopes != expected_scopes:
        missing = sorted(scope.value for scope in expected_scopes - actual_scopes)
        extra = sorted(scope.value for scope in actual_scopes - expected_scopes)
        raise RuntimeError(
            f"InternalTelemetryBench v1 scope mismatch: missing={missing}, extra={extra}"
        )
    if len(scenarios) != 30:
        raise RuntimeError(f"InternalTelemetryBench v1 expected 30 scenarios, got {len(scenarios)}")
    return scenarios
