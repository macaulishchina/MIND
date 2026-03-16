from __future__ import annotations

import json
from pathlib import Path

import pytest

from mind.access import (
    AccessAutoAuditResult,
    AccessBenchmarkResult,
    AccessContextKind,
    AccessFrontierComparison,
    AccessGateResult,
    AccessMode,
    AccessModeFamilyAggregate,
    AccessModeTraceEvent,
    AccessReasonCode,
    AccessRunResponse,
    AccessRunTrace,
    AccessSwitchKind,
    AccessTaskFamily,
    AccessTraceKind,
    assert_access_gate,
    build_access_gate_result,
    evaluate_access_gate,
    write_access_gate_report_json,
)


def test_phase_i_gate_builds_full_result_from_component_evaluations() -> None:
    result = _passing_gate_result()

    assert_access_gate(result)
    assert result.i1_pass
    assert result.i2_pass
    assert result.i3_pass
    assert result.i4_pass
    assert result.i5_pass
    assert result.i6_pass
    assert result.i7_pass
    assert result.i8_pass
    assert result.access_gate_pass
    assert set(result.callable_modes) == {
        AccessMode.AUTO,
        AccessMode.FLASH,
        AccessMode.RECALL,
        AccessMode.RECONSTRUCT,
        AccessMode.REFLECTIVE_ACCESS,
    }


def test_phase_i_gate_report_writes_json(tmp_path: Path) -> None:
    result = _passing_gate_result()

    output_path = write_access_gate_report_json(tmp_path / "phase_i_report.json", result)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "access_gate_report_v1"
    assert payload["access_gate_pass"] is True
    assert sorted(payload["callable_modes"]) == [
        "auto",
        "flash",
        "recall",
        "reconstruct",
        "reflective_access",
    ]
    assert payload["auto_audit"]["upgrade_count"] > 0
    assert payload["auto_audit"]["downgrade_count"] > 0
    assert payload["auto_audit"]["jump_count"] > 0


def test_phase_i_gate_composes_public_evaluation_from_components(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    benchmark_result = _passing_benchmark_result()
    fixed_runs = _passing_fixed_runs()
    audit_result = _passing_auto_audit_result()
    captured: dict[str, object] = {}

    def fake_benchmark(
        *,
        db_path: Path | None = None,
        store_factory: object | None = None,
    ) -> AccessBenchmarkResult:
        captured["benchmark_db_path"] = db_path
        captured["benchmark_store_factory"] = store_factory
        return benchmark_result

    def fake_fixed_lock(
        db_path: Path | None = None,
        store_factory: object | None = None,
    ) -> tuple[AccessRunResponse, ...]:
        captured["fixed_lock_db_path"] = db_path
        captured["fixed_lock_store_factory"] = store_factory
        return fixed_runs

    def fake_auto_audit(
        db_path: Path | None = None,
        store_factory: object | None = None,
    ) -> AccessAutoAuditResult:
        captured["auto_audit_db_path"] = db_path
        captured["auto_audit_store_factory"] = store_factory
        return audit_result

    monkeypatch.setattr("mind.access.gate.evaluate_access_benchmark", fake_benchmark)
    monkeypatch.setattr("mind.access.gate.evaluate_access_fixed_lock_audit", fake_fixed_lock)
    monkeypatch.setattr("mind.access.gate.evaluate_access_auto_audit", fake_auto_audit)

    db_path = tmp_path / "phase_i_gate.sqlite3"
    result = evaluate_access_gate(db_path)

    assert result.access_gate_pass
    assert captured == {
        "benchmark_db_path": tmp_path / "phase_i_gate_bench.sqlite3",
        "benchmark_store_factory": None,
        "fixed_lock_db_path": db_path,
        "fixed_lock_store_factory": None,
        "auto_audit_db_path": db_path,
        "auto_audit_store_factory": None,
    }


def test_phase_i_gate_result_uses_all_benchmark_families() -> None:
    result = _passing_gate_result()

    families = {aggregate.task_family for aggregate in result.mode_family_aggregates}
    assert families == {
        AccessTaskFamily.SPEED_SENSITIVE,
        AccessTaskFamily.BALANCED,
        AccessTaskFamily.HIGH_CORRECTNESS,
    }


def _passing_gate_result() -> AccessGateResult:
    return build_access_gate_result(
        benchmark_result=_passing_benchmark_result(),
        fixed_runs=_passing_fixed_runs(),
        auto_audit=_passing_auto_audit_result(),
    )


def _passing_benchmark_result() -> AccessBenchmarkResult:
    return AccessBenchmarkResult(
        case_count=60,
        run_count=300,
        runs=(),
        mode_family_aggregates=(
            _aggregate(
                mode=AccessMode.FLASH,
                family=AccessTaskFamily.SPEED_SENSITIVE,
                time_budget_hit_rate=0.96,
                constraint_satisfaction=0.90,
            ),
            _aggregate(
                mode=AccessMode.RECALL,
                family=AccessTaskFamily.BALANCED,
                answer_quality_score=0.76,
                memory_use_score=0.66,
            ),
            _aggregate(
                mode=AccessMode.RECONSTRUCT,
                family=AccessTaskFamily.HIGH_CORRECTNESS,
                answer_faithfulness=0.96,
                gold_fact_coverage=0.91,
            ),
            _aggregate(
                mode=AccessMode.REFLECTIVE_ACCESS,
                family=AccessTaskFamily.HIGH_CORRECTNESS,
                constraint_satisfaction=0.99,
                gold_fact_coverage=0.93,
                answer_faithfulness=0.98,
            ),
        ),
        frontier_comparisons=(
            _frontier(AccessTaskFamily.SPEED_SENSITIVE, AccessMode.FLASH),
            _frontier(AccessTaskFamily.BALANCED, AccessMode.RECALL),
            _frontier(AccessTaskFamily.HIGH_CORRECTNESS, AccessMode.REFLECTIVE_ACCESS),
        ),
    )


def _aggregate(
    mode: AccessMode,
    family: AccessTaskFamily,
    *,
    time_budget_hit_rate: float = 1.0,
    constraint_satisfaction: float = 1.0,
    gold_fact_coverage: float = 1.0,
    answer_faithfulness: float = 1.0,
    answer_quality_score: float = 1.0,
    memory_use_score: float = 1.0,
) -> AccessModeFamilyAggregate:
    return AccessModeFamilyAggregate(
        requested_mode=mode,
        task_family=family,
        run_count=20,
        time_budget_hit_rate=time_budget_hit_rate,
        task_completion_score=1.0,
        constraint_satisfaction=constraint_satisfaction,
        gold_fact_coverage=gold_fact_coverage,
        answer_faithfulness=answer_faithfulness,
        answer_quality_score=answer_quality_score,
        needed_memory_recall_at_20=1.0,
        workspace_support_precision=1.0,
        answer_trace_support=1.0,
        memory_use_score=memory_use_score,
        online_cost_ratio=1.0,
        cost_efficiency_score=0.75,
    )


def _frontier(family: AccessTaskFamily, mode: AccessMode) -> AccessFrontierComparison:
    return AccessFrontierComparison(
        task_family=family,
        family_best_fixed_mode=mode,
        family_best_fixed_aqs=0.80,
        family_best_fixed_cost_efficiency_score=0.70,
        auto_aqs=0.79,
        auto_cost_efficiency_score=0.71,
        auto_aqs_drop=0.01,
    )


def _passing_fixed_runs() -> tuple[AccessRunResponse, ...]:
    return (
        _fixed_run(AccessMode.FLASH, AccessTaskFamily.SPEED_SENSITIVE),
        _fixed_run(AccessMode.RECALL, AccessTaskFamily.BALANCED),
        _fixed_run(AccessMode.RECONSTRUCT, AccessTaskFamily.HIGH_CORRECTNESS),
        _fixed_run(AccessMode.REFLECTIVE_ACCESS, AccessTaskFamily.HIGH_CORRECTNESS),
    )


def _fixed_run(mode: AccessMode, family: AccessTaskFamily) -> AccessRunResponse:
    selected_object_ids = [] if mode is AccessMode.FLASH else ["obj-1"]
    selected_summaries = [] if mode is AccessMode.FLASH else [{"object_id": "obj-1"}]
    verification_notes = ["verified"] if mode is AccessMode.REFLECTIVE_ACCESS else []
    context_kind = (
        AccessContextKind.RAW_TOPK if mode is AccessMode.FLASH else AccessContextKind.WORKSPACE
    )

    return AccessRunResponse(
        resolved_mode=mode,
        context_kind=context_kind,
        context_object_ids=["obj-1"],
        context_text="context",
        context_token_count=42,
        candidate_ids=["obj-1"],
        candidate_summaries=[],
        read_object_ids=["obj-1"],
        expanded_object_ids=[],
        selected_object_ids=selected_object_ids,
        selected_summaries=selected_summaries,
        answer_text="answer",
        answer_support_ids=["obj-1"],
        answer_trace=None,
        verification_notes=verification_notes,
        trace=AccessRunTrace(
            requested_mode=mode,
            resolved_mode=mode,
            task_family=family,
            events=[
                AccessModeTraceEvent(
                    event_kind=AccessTraceKind.SELECT_MODE,
                    mode=mode,
                    summary="selected explicit mode",
                    reason_code=AccessReasonCode.EXPLICIT_MODE_REQUEST,
                    switch_kind=AccessSwitchKind.INITIAL,
                ),
                AccessModeTraceEvent(
                    event_kind=AccessTraceKind.MODE_SUMMARY,
                    mode=mode,
                    summary="completed mode execution",
                ),
            ],
        ),
        used_object_ids=["obj-1"],
    )


def _passing_auto_audit_result() -> AccessAutoAuditResult:
    return AccessAutoAuditResult(
        audited_run_count=24,
        switch_run_count=12,
        total_switch_count=12,
        upgrade_count=5,
        downgrade_count=4,
        jump_count=3,
        missing_reason_code_count=0,
        missing_summary_count=0,
        oscillation_case_count=0,
    )
