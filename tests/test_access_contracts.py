from __future__ import annotations

from collections import Counter

import pytest

from mind.access import (
    AccessContextKind,
    AccessMode,
    AccessModeRequest,
    AccessModeTraceEvent,
    AccessReasonCode,
    AccessRunResponse,
    AccessRunTrace,
    AccessSwitchKind,
    AccessTaskFamily,
    AccessTraceKind,
)
from mind.fixtures.access_depth_bench import build_access_depth_bench_v1


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


def _trace_event(
    *,
    event_kind: AccessTraceKind,
    mode: AccessMode,
    summary: str,
) -> AccessModeTraceEvent:
    return AccessModeTraceEvent(event_kind=event_kind, mode=mode, summary=summary)


def test_access_mode_request_defaults_to_auto() -> None:
    request = AccessModeRequest()

    assert request.requested_mode is AccessMode.AUTO
    assert request.task_family is None
    assert request.hard_constraints == []


def test_trace_events_reject_auto_mode() -> None:
    with pytest.raises(ValueError, match="effective fixed access mode"):
        AccessModeTraceEvent(
            event_kind=AccessTraceKind.READ,
            mode=AccessMode.AUTO,
            summary="invalid",
        )


def test_fixed_mode_trace_rejects_override() -> None:
    with pytest.raises(ValueError, match="must not be overridden"):
        AccessRunTrace(
            requested_mode=AccessMode.RECALL,
            resolved_mode=AccessMode.RECONSTRUCT,
            events=[
                _select_event(
                    mode=AccessMode.RECALL,
                    reason_code=AccessReasonCode.EXPLICIT_MODE_REQUEST,
                    switch_kind=AccessSwitchKind.INITIAL,
                    summary="user locked recall",
                ),
                _trace_event(
                    event_kind=AccessTraceKind.MODE_SUMMARY,
                    mode=AccessMode.RECONSTRUCT,
                    summary="finished deeper",
                ),
            ],
        )


def test_fixed_mode_trace_rejects_extra_select_events() -> None:
    with pytest.raises(ValueError, match="must not contain auto-driven mode switches"):
        AccessRunTrace(
            requested_mode=AccessMode.RECALL,
            resolved_mode=AccessMode.RECALL,
            events=[
                _select_event(
                    mode=AccessMode.RECALL,
                    reason_code=AccessReasonCode.EXPLICIT_MODE_REQUEST,
                    switch_kind=AccessSwitchKind.INITIAL,
                    summary="user locked recall",
                ),
                _select_event(
                    mode=AccessMode.RECONSTRUCT,
                    reason_code=AccessReasonCode.COVERAGE_INSUFFICIENT,
                    switch_kind=AccessSwitchKind.UPGRADE,
                    from_mode=AccessMode.RECALL,
                    summary="invalid auto override",
                ),
                _trace_event(
                    event_kind=AccessTraceKind.MODE_SUMMARY,
                    mode=AccessMode.RECALL,
                    summary="finished",
                ),
            ],
        )


def test_auto_trace_accepts_upgrade_sequence() -> None:
    trace = AccessRunTrace(
        requested_mode=AccessMode.AUTO,
        resolved_mode=AccessMode.REFLECTIVE_ACCESS,
        task_family=AccessTaskFamily.HIGH_CORRECTNESS,
        time_budget_ms=1500,
        hard_constraints=["must verify contradictions"],
        events=[
            _select_event(
                mode=AccessMode.RECALL,
                reason_code=AccessReasonCode.BALANCED_DEFAULT,
                switch_kind=AccessSwitchKind.INITIAL,
                summary="start balanced",
            ),
            _trace_event(
                event_kind=AccessTraceKind.RETRIEVE,
                mode=AccessMode.RECALL,
                summary="retrieved summary and task episode",
            ),
            _select_event(
                mode=AccessMode.REFLECTIVE_ACCESS,
                reason_code=AccessReasonCode.EVIDENCE_CONFLICT,
                switch_kind=AccessSwitchKind.JUMP,
                from_mode=AccessMode.RECALL,
                summary="contradiction requires deeper verification",
            ),
            _trace_event(
                event_kind=AccessTraceKind.VERIFY,
                mode=AccessMode.REFLECTIVE_ACCESS,
                summary="verified conflicting supports",
            ),
            _trace_event(
                event_kind=AccessTraceKind.MODE_SUMMARY,
                mode=AccessMode.REFLECTIVE_ACCESS,
                summary="resolved after reflective verification",
            ),
        ],
    )

    assert trace.resolved_mode is AccessMode.REFLECTIVE_ACCESS
    assert trace.events[1].event_kind is AccessTraceKind.RETRIEVE


def test_trace_requires_select_mode_then_summary() -> None:
    with pytest.raises(ValueError, match="must start with select_mode"):
        AccessRunTrace(
            requested_mode=AccessMode.AUTO,
            resolved_mode=AccessMode.RECALL,
            events=[
                _trace_event(
                    event_kind=AccessTraceKind.READ,
                    mode=AccessMode.RECALL,
                    summary="read summary first",
                ),
                _trace_event(
                    event_kind=AccessTraceKind.MODE_SUMMARY,
                    mode=AccessMode.RECALL,
                    summary="done",
                ),
            ],
        )


def test_access_depth_bench_v1_is_frozen_to_sixty_cases() -> None:
    cases = build_access_depth_bench_v1()

    assert len(cases) == 60
    assert Counter(case.task_family for case in cases) == {
        AccessTaskFamily.SPEED_SENSITIVE: 20,
        AccessTaskFamily.BALANCED: 20,
        AccessTaskFamily.HIGH_CORRECTNESS: 20,
    }
    assert all(case.hard_constraints for case in cases)
    assert all(case.required_fragments for case in cases)
    assert all(case.gold_fact_ids for case in cases)
    assert all(case.gold_memory_refs for case in cases)


def test_access_depth_bench_failure_cases_require_reflective_mode() -> None:
    cases = build_access_depth_bench_v1()
    case = next(
        sample
        for sample in cases
        if sample.case_id == "episode-004_high_correctness_detailed"
    )

    assert case.task_family is AccessTaskFamily.HIGH_CORRECTNESS
    assert case.recommended_mode is AccessMode.REFLECTIVE_ACCESS
    assert any("stale memory" in fragment for fragment in case.required_fragments)


# --- Phase I independent audit supplementary tests ---


def _locked_trace(
    *,
    mode: AccessMode,
    summary_mode: AccessMode | None = None,
) -> AccessRunTrace:
    """Helper to build a minimal valid fixed-mode trace."""
    effective = summary_mode or mode
    return AccessRunTrace(
        requested_mode=mode,
        resolved_mode=effective,
        events=[
            _select_event(
                mode=mode,
                reason_code=AccessReasonCode.EXPLICIT_MODE_REQUEST,
                switch_kind=AccessSwitchKind.INITIAL,
                summary=f"locked {mode.value}",
            ),
            _trace_event(
                event_kind=AccessTraceKind.RETRIEVE,
                mode=mode,
                summary="retrieved",
            ),
            _trace_event(
                event_kind=AccessTraceKind.MODE_SUMMARY,
                mode=effective,
                summary="done",
            ),
        ],
    )


def test_response_rejects_flash_with_workspace_context() -> None:
    with pytest.raises(ValueError, match="flash mode must not return a workspace context"):
        AccessRunResponse(
            resolved_mode=AccessMode.FLASH,
            context_kind=AccessContextKind.WORKSPACE,
            context_object_ids=["obj-1"],
            context_text='{"slots": []}',
            context_token_count=10,
            selected_object_ids=["obj-1"],
            trace=_locked_trace(mode=AccessMode.FLASH),
        )


def test_response_rejects_non_flash_with_raw_topk_context() -> None:
    with pytest.raises(ValueError, match="raw_topk context is only valid for flash mode"):
        AccessRunResponse(
            resolved_mode=AccessMode.RECALL,
            context_kind=AccessContextKind.RAW_TOPK,
            context_object_ids=["obj-1"],
            context_text='{"objects": []}',
            context_token_count=10,
            trace=_locked_trace(mode=AccessMode.RECALL),
        )


def test_response_rejects_reflective_without_verification_notes() -> None:
    reflective_trace = AccessRunTrace(
        requested_mode=AccessMode.REFLECTIVE_ACCESS,
        resolved_mode=AccessMode.REFLECTIVE_ACCESS,
        events=[
            _select_event(
                mode=AccessMode.REFLECTIVE_ACCESS,
                reason_code=AccessReasonCode.EXPLICIT_MODE_REQUEST,
                switch_kind=AccessSwitchKind.INITIAL,
                summary="locked reflective",
            ),
            _trace_event(
                event_kind=AccessTraceKind.MODE_SUMMARY,
                mode=AccessMode.REFLECTIVE_ACCESS,
                summary="done",
            ),
        ],
    )
    with pytest.raises(ValueError, match="reflective access responses require verification notes"):
        AccessRunResponse(
            resolved_mode=AccessMode.REFLECTIVE_ACCESS,
            context_kind=AccessContextKind.WORKSPACE,
            context_object_ids=["obj-1"],
            context_text='{"slots": []}',
            context_token_count=10,
            selected_object_ids=["obj-1"],
            verification_notes=[],
            trace=reflective_trace,
        )


def test_response_rejects_non_reflective_with_verification_notes() -> None:
    with pytest.raises(ValueError, match="only reflective access may define verification notes"):
        AccessRunResponse(
            resolved_mode=AccessMode.RECALL,
            context_kind=AccessContextKind.WORKSPACE,
            context_object_ids=["obj-1"],
            context_text='{"slots": []}',
            context_token_count=10,
            selected_object_ids=["obj-1"],
            verification_notes=["spurious note"],
            trace=_locked_trace(mode=AccessMode.RECALL),
        )


def test_response_rejects_resolved_mode_auto() -> None:
    with pytest.raises(ValueError, match="resolved_mode must be a fixed access mode"):
        AccessRunResponse(
            resolved_mode=AccessMode.AUTO,
            context_kind=AccessContextKind.RAW_TOPK,
            context_object_ids=["obj-1"],
            context_text='{"objects": []}',
            context_token_count=10,
            trace=AccessRunTrace(
                requested_mode=AccessMode.AUTO,
                resolved_mode=AccessMode.FLASH,
                events=[
                    _select_event(
                        mode=AccessMode.FLASH,
                        reason_code=AccessReasonCode.LATENCY_SENSITIVE,
                        switch_kind=AccessSwitchKind.INITIAL,
                        summary="auto chose flash",
                    ),
                    _trace_event(
                        event_kind=AccessTraceKind.MODE_SUMMARY,
                        mode=AccessMode.FLASH,
                        summary="done",
                    ),
                ],
            ),
        )


def test_response_rejects_workspace_without_selected_ids() -> None:
    with pytest.raises(ValueError, match="workspace responses require selected_object_ids"):
        AccessRunResponse(
            resolved_mode=AccessMode.RECALL,
            context_kind=AccessContextKind.WORKSPACE,
            context_object_ids=["obj-1"],
            context_text='{"slots": []}',
            context_token_count=10,
            selected_object_ids=[],
            trace=_locked_trace(mode=AccessMode.RECALL),
        )


def test_switch_event_rejects_same_from_and_target_mode() -> None:
    with pytest.raises(ValueError, match="mode switches must change the effective mode"):
        AccessModeTraceEvent(
            event_kind=AccessTraceKind.SELECT_MODE,
            mode=AccessMode.RECALL,
            summary="no-op switch",
            reason_code=AccessReasonCode.COVERAGE_INSUFFICIENT,
            switch_kind=AccessSwitchKind.UPGRADE,
            from_mode=AccessMode.RECALL,
        )


def test_non_initial_switch_requires_from_mode() -> None:
    with pytest.raises(ValueError, match="non-initial select_mode events require from_mode"):
        AccessModeTraceEvent(
            event_kind=AccessTraceKind.SELECT_MODE,
            mode=AccessMode.RECALL,
            summary="upgrade without origin",
            reason_code=AccessReasonCode.COVERAGE_INSUFFICIENT,
            switch_kind=AccessSwitchKind.UPGRADE,
        )


def test_non_select_event_rejects_switch_metadata() -> None:
    with pytest.raises(ValueError, match="only select_mode events may define switch metadata"):
        AccessModeTraceEvent(
            event_kind=AccessTraceKind.READ,
            mode=AccessMode.RECALL,
            summary="read with spurious switch",
            switch_kind=AccessSwitchKind.UPGRADE,
        )


def test_trace_rejects_missing_final_mode_summary() -> None:
    with pytest.raises(ValueError, match="must end with mode_summary"):
        AccessRunTrace(
            requested_mode=AccessMode.AUTO,
            resolved_mode=AccessMode.RECALL,
            events=[
                _select_event(
                    mode=AccessMode.RECALL,
                    reason_code=AccessReasonCode.BALANCED_DEFAULT,
                    switch_kind=AccessSwitchKind.INITIAL,
                    summary="start",
                ),
                _trace_event(
                    event_kind=AccessTraceKind.READ,
                    mode=AccessMode.RECALL,
                    summary="read objects",
                ),
            ],
        )


def test_trace_final_summary_must_match_resolved_mode() -> None:
    with pytest.raises(ValueError, match="final mode_summary must match resolved_mode"):
        AccessRunTrace(
            requested_mode=AccessMode.AUTO,
            resolved_mode=AccessMode.RECALL,
            events=[
                _select_event(
                    mode=AccessMode.RECALL,
                    reason_code=AccessReasonCode.BALANCED_DEFAULT,
                    switch_kind=AccessSwitchKind.INITIAL,
                    summary="start",
                ),
                _trace_event(
                    event_kind=AccessTraceKind.MODE_SUMMARY,
                    mode=AccessMode.FLASH,
                    summary="wrong mode summary",
                ),
            ],
        )


def test_access_depth_bench_v1_task_families_are_balanced() -> None:
    """Each task family should have exactly 20 cases."""
    cases = build_access_depth_bench_v1()
    families = Counter(case.task_family for case in cases)

    for family in AccessTaskFamily:
        assert families[family] == 20, f"{family.value} has {families[family]} cases, expected 20"

    assert len(set(case.case_id for case in cases)) == 60, "case IDs must be unique"
