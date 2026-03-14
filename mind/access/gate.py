"""Runtime access formal gate evaluation helpers."""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mind.fixtures.access_depth_bench import build_access_depth_bench_v1
from mind.fixtures.retrieval_benchmark import build_canonical_seed_objects
from mind.kernel.store import MemoryStoreFactory, SQLiteMemoryStore
from mind.primitives.contracts import Capability, PrimitiveExecutionContext

from .benchmark import (
    AccessFrontierComparison,
    AccessModeFamilyAggregate,
    evaluate_access_benchmark,
)
from .contracts import (
    AccessMode,
    AccessRunResponse,
    AccessSwitchKind,
    AccessTaskFamily,
    AccessTraceKind,
)
from .service import AccessService

_SCHEMA_VERSION = "access_gate_report_v1"
_FIXED_TIMESTAMP = datetime(2026, 3, 10, 18, 0, tzinfo=UTC)


@dataclass(frozen=True)
class AccessAutoAuditResult:
    audited_run_count: int
    switch_run_count: int
    total_switch_count: int
    upgrade_count: int
    downgrade_count: int
    jump_count: int
    missing_reason_code_count: int
    missing_summary_count: int
    oscillation_case_count: int


@dataclass(frozen=True)
class AccessGateResult:
    case_count: int
    benchmark_run_count: int
    callable_modes: tuple[AccessMode, ...]
    trace_coverage_count: int
    trace_total: int
    fixed_lock_run_count: int
    fixed_lock_override_count: int
    flash_time_budget_hit_rate: float
    flash_constraint_satisfaction: float
    recall_answer_quality_score: float
    recall_memory_use_score: float
    reconstruct_answer_faithfulness: float
    reconstruct_gold_fact_coverage: float
    reflective_answer_faithfulness: float
    reflective_gold_fact_coverage: float
    reflective_constraint_satisfaction: float
    auto_frontier_average_aqs_drop: float
    auto_frontier_cost_regression_count: int
    auto_audit: AccessAutoAuditResult
    mode_family_aggregates: tuple[AccessModeFamilyAggregate, ...]
    frontier_comparisons: tuple[AccessFrontierComparison, ...]

    @property
    def i1_pass(self) -> bool:
        return (
            len(set(self.callable_modes)) == 5
            and self.trace_total > 0
            and self.trace_coverage_count == self.trace_total
        )

    @property
    def i2_pass(self) -> bool:
        return (
            self.flash_time_budget_hit_rate >= 0.95 and self.flash_constraint_satisfaction >= 0.85
        )

    @property
    def i3_pass(self) -> bool:
        return self.recall_answer_quality_score >= 0.75 and self.recall_memory_use_score >= 0.65

    @property
    def i4_pass(self) -> bool:
        return (
            self.reconstruct_answer_faithfulness >= 0.95
            and self.reconstruct_gold_fact_coverage >= 0.90
        )

    @property
    def i5_pass(self) -> bool:
        return (
            self.reflective_answer_faithfulness >= 0.97
            and self.reflective_gold_fact_coverage >= 0.92
            and self.reflective_constraint_satisfaction >= 0.98
        )

    @property
    def i6_pass(self) -> bool:
        return (
            self.auto_frontier_average_aqs_drop <= 0.02
            and self.auto_frontier_cost_regression_count == 0
        )

    @property
    def i7_pass(self) -> bool:
        audit = self.auto_audit
        oscillation_rate = (
            audit.oscillation_case_count / float(audit.audited_run_count)
            if audit.audited_run_count
            else 1.0
        )
        return (
            audit.upgrade_count > 0
            and audit.downgrade_count > 0
            and audit.jump_count > 0
            and audit.missing_reason_code_count == 0
            and audit.missing_summary_count == 0
            and oscillation_rate <= 0.05
        )

    @property
    def i8_pass(self) -> bool:
        return self.fixed_lock_run_count > 0 and self.fixed_lock_override_count == 0

    @property
    def access_gate_pass(self) -> bool:
        return (
            self.i1_pass
            and self.i2_pass
            and self.i3_pass
            and self.i4_pass
            and self.i5_pass
            and self.i6_pass
            and self.i7_pass
            and self.i8_pass
        )


def evaluate_access_gate(
    db_path: str | Path | None = None,
    store_factory: MemoryStoreFactory | None = None,
) -> AccessGateResult:
    """Run the formal runtime access gate."""

    def default_store_factory(store_path: Path) -> SQLiteMemoryStore:
        return SQLiteMemoryStore(store_path)

    def run(store_path: Path, active_store_factory: MemoryStoreFactory) -> AccessGateResult:
        benchmark_result = evaluate_access_benchmark(
            db_path=store_path.with_name(f"{store_path.stem}_bench.sqlite3"),
            store_factory=active_store_factory,
        )
        aggregate_lookup = {
            (aggregate.requested_mode, aggregate.task_family): aggregate
            for aggregate in benchmark_result.mode_family_aggregates
        }
        flash_speed = aggregate_lookup[(AccessMode.FLASH, AccessTaskFamily.SPEED_SENSITIVE)]
        recall_balanced = aggregate_lookup[(AccessMode.RECALL, AccessTaskFamily.BALANCED)]
        reconstruct_high = aggregate_lookup[
            (AccessMode.RECONSTRUCT, AccessTaskFamily.HIGH_CORRECTNESS)
        ]
        reflective_high = aggregate_lookup[
            (AccessMode.REFLECTIVE_ACCESS, AccessTaskFamily.HIGH_CORRECTNESS)
        ]
        average_aqs_drop = round(
            sum(comparison.auto_aqs_drop for comparison in benchmark_result.frontier_comparisons)
            / float(len(benchmark_result.frontier_comparisons)),
            4,
        )
        auto_cost_regression_count = sum(
            comparison.auto_cost_efficiency_score
            < comparison.family_best_fixed_cost_efficiency_score
            for comparison in benchmark_result.frontier_comparisons
        )

        with active_store_factory(store_path) as store:
            store.insert_objects(build_canonical_seed_objects())
            access_service = AccessService(store, clock=lambda: _FIXED_TIMESTAMP)
            fixed_runs = _run_fixed_lock_audit(access_service)
            auto_audit = _run_auto_audit(access_service)

        trace_total = len(fixed_runs) + auto_audit.audited_run_count
        trace_coverage_count = sum(_trace_is_complete(run) for run in fixed_runs)
        trace_coverage_count += auto_audit.audited_run_count
        fixed_lock_override_count = sum(_fixed_lock_overridden(run) for run in fixed_runs)
        callable_modes = tuple(
            sorted(
                {
                    *(run.trace.requested_mode for run in fixed_runs),
                    AccessMode.AUTO,
                },
                key=lambda mode: mode.value,
            )
        )

        return AccessGateResult(
            case_count=benchmark_result.case_count,
            benchmark_run_count=benchmark_result.run_count,
            callable_modes=callable_modes,
            trace_coverage_count=trace_coverage_count,
            trace_total=trace_total,
            fixed_lock_run_count=len(fixed_runs),
            fixed_lock_override_count=fixed_lock_override_count,
            flash_time_budget_hit_rate=flash_speed.time_budget_hit_rate,
            flash_constraint_satisfaction=flash_speed.constraint_satisfaction,
            recall_answer_quality_score=recall_balanced.answer_quality_score,
            recall_memory_use_score=recall_balanced.memory_use_score,
            reconstruct_answer_faithfulness=reconstruct_high.answer_faithfulness,
            reconstruct_gold_fact_coverage=reconstruct_high.gold_fact_coverage,
            reflective_answer_faithfulness=reflective_high.answer_faithfulness,
            reflective_gold_fact_coverage=reflective_high.gold_fact_coverage,
            reflective_constraint_satisfaction=reflective_high.constraint_satisfaction,
            auto_frontier_average_aqs_drop=average_aqs_drop,
            auto_frontier_cost_regression_count=auto_cost_regression_count,
            auto_audit=auto_audit,
            mode_family_aggregates=benchmark_result.mode_family_aggregates,
            frontier_comparisons=benchmark_result.frontier_comparisons,
        )

    active_factory = store_factory or default_store_factory
    if db_path is not None:
        return run(Path(db_path), active_factory)

    with tempfile.TemporaryDirectory() as tmpdir:
        return run(Path(tmpdir) / "access_gate.sqlite3", active_factory)


def assert_access_gate(result: AccessGateResult) -> None:
    if not result.i1_pass:
        raise RuntimeError(
            "I-1 failed: access mode contract drift "
            f"(callable_modes={len(set(result.callable_modes))}/5, "
            f"trace_coverage={result.trace_coverage_count}/{result.trace_total})"
        )
    if not result.i2_pass:
        raise RuntimeError(
            "I-2 failed: flash floor missed "
            f"(time_budget_hit_rate={result.flash_time_budget_hit_rate:.4f}, "
            "constraint_satisfaction="
            f"{result.flash_constraint_satisfaction:.4f})"
        )
    if not result.i3_pass:
        raise RuntimeError(
            "I-3 failed: recall floor missed "
            f"(aqs={result.recall_answer_quality_score:.4f}, "
            f"mus={result.recall_memory_use_score:.4f})"
        )
    if not result.i4_pass:
        raise RuntimeError(
            "I-4 failed: reconstruct floor missed "
            f"(faithfulness={result.reconstruct_answer_faithfulness:.4f}, "
            f"gold_fact_coverage={result.reconstruct_gold_fact_coverage:.4f})"
        )
    if not result.i5_pass:
        raise RuntimeError(
            "I-5 failed: reflective floor missed "
            f"(faithfulness={result.reflective_answer_faithfulness:.4f}, "
            f"gold_fact_coverage={result.reflective_gold_fact_coverage:.4f}, "
            "constraint_satisfaction="
            f"{result.reflective_constraint_satisfaction:.4f})"
        )
    if not result.i6_pass:
        raise RuntimeError(
            "I-6 failed: auto frontier regression "
            f"(average_aqs_drop={result.auto_frontier_average_aqs_drop:.4f}, "
            "cost_regressions="
            f"{result.auto_frontier_cost_regression_count})"
        )
    if not result.i7_pass:
        raise RuntimeError(
            "I-7 failed: auto audit drift "
            f"(upgrade={result.auto_audit.upgrade_count}, "
            f"downgrade={result.auto_audit.downgrade_count}, "
            f"jump={result.auto_audit.jump_count}, "
            "missing_reason_codes="
            f"{result.auto_audit.missing_reason_code_count}, "
            f"missing_summaries={result.auto_audit.missing_summary_count}, "
            f"oscillation_cases={result.auto_audit.oscillation_case_count})"
        )
    if not result.i8_pass:
        raise RuntimeError(
            "I-8 failed: explicit mode lock was overridden "
            f"({result.fixed_lock_override_count}/{result.fixed_lock_run_count})"
        )


def write_access_gate_report_json(
    path: str | Path,
    result: AccessGateResult,
) -> Path:
    """Persist the full runtime access gate result as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        **asdict(result),
        "i1_pass": result.i1_pass,
        "i2_pass": result.i2_pass,
        "i3_pass": result.i3_pass,
        "i4_pass": result.i4_pass,
        "i5_pass": result.i5_pass,
        "i6_pass": result.i6_pass,
        "i7_pass": result.i7_pass,
        "i8_pass": result.i8_pass,
        "access_gate_pass": result.access_gate_pass,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def _run_fixed_lock_audit(access_service: AccessService) -> list[AccessRunResponse]:
    fixed_runs: list[AccessRunResponse] = []
    cases = build_access_depth_bench_v1()
    for requested_mode in (
        AccessMode.FLASH,
        AccessMode.RECALL,
        AccessMode.RECONSTRUCT,
        AccessMode.REFLECTIVE_ACCESS,
    ):
        for case in cases:
            fixed_runs.append(
                access_service.run(
                    {
                        "requested_mode": requested_mode.value,
                        "task_id": case.task_id,
                        "task_family": case.task_family.value,
                        "time_budget_ms": case.time_budget_ms,
                        "hard_constraints": list(case.hard_constraints),
                        "query": case.prompt,
                        "filters": {"episode_id": case.episode_id},
                    },
                    _context(actor=f"phase-i-fixed::{requested_mode.value}::{case.case_id}"),
                )
            )
    return fixed_runs


def _run_auto_audit(access_service: AccessService) -> AccessAutoAuditResult:
    auto_runs: list[AccessRunResponse] = []
    for case in build_access_depth_bench_v1():
        auto_runs.append(
            access_service.run(
                {
                    "requested_mode": AccessMode.AUTO.value,
                    "task_id": case.task_id,
                    "task_family": case.task_family.value,
                    "time_budget_ms": case.time_budget_ms,
                    "hard_constraints": list(case.hard_constraints),
                    "query": case.prompt,
                    "filters": {"episode_id": case.episode_id},
                },
                _context(actor=f"phase-i-auto::{case.case_id}"),
            )
        )

    targeted_requests: tuple[dict[str, Any], ...] = (
        {
            "requested_mode": "auto",
            "task_id": "task-004",
            "task_family": "speed_sensitive",
            "time_budget_ms": 150,
            "hard_constraints": ["must include the latest episode summary"],
            "query": "Episode 4 revised corrected replay hints",
            "query_modes": ["keyword"],
            "filters": {"object_types": ["SummaryNote", "TaskEpisode"]},
        },
        {
            "requested_mode": "auto",
            "task_id": "showcase-task",
            "task_family": "speed_sensitive",
            "time_budget_ms": 500,
            "query": "showcase episode",
            "query_modes": ["keyword"],
            "filters": {"object_types": ["TaskEpisode"], "task_id": "showcase-task"},
        },
        {
            "requested_mode": "auto",
            "task_id": "task-008",
            "task_family": "high_correctness",
            "query": "Episode 8 stale memory revalidated",
            "query_modes": ["keyword"],
            "filters": {
                "object_types": ["ReflectionNote", "SummaryNote", "TaskEpisode", "RawRecord"]
            },
        },
    )
    for index, request in enumerate(targeted_requests, start=1):
        auto_runs.append(
            access_service.run(
                request,
                _context(actor=f"phase-i-auto-targeted::{index}"),
            )
        )

    total_switch_count = 0
    switch_run_count = 0
    upgrade_count = 0
    downgrade_count = 0
    jump_count = 0
    missing_reason_code_count = 0
    missing_summary_count = 0
    oscillation_case_count = 0

    for run in auto_runs:
        select_events = [
            event for event in run.trace.events if event.event_kind is AccessTraceKind.SELECT_MODE
        ]
        switch_events = [
            event for event in select_events if event.switch_kind is not AccessSwitchKind.INITIAL
        ]
        if switch_events:
            switch_run_count += 1
        total_switch_count += len(switch_events)
        for event in switch_events:
            if event.switch_kind is AccessSwitchKind.UPGRADE:
                upgrade_count += 1
            elif event.switch_kind is AccessSwitchKind.DOWNGRADE:
                downgrade_count += 1
            elif event.switch_kind is AccessSwitchKind.JUMP:
                jump_count += 1
            if event.reason_code is None:
                missing_reason_code_count += 1
            if not event.summary.strip():
                missing_summary_count += 1

        visited_modes = [event.mode for event in select_events]
        if len(set(visited_modes)) != len(visited_modes):
            oscillation_case_count += 1

    return AccessAutoAuditResult(
        audited_run_count=len(auto_runs),
        switch_run_count=switch_run_count,
        total_switch_count=total_switch_count,
        upgrade_count=upgrade_count,
        downgrade_count=downgrade_count,
        jump_count=jump_count,
        missing_reason_code_count=missing_reason_code_count,
        missing_summary_count=missing_summary_count,
        oscillation_case_count=oscillation_case_count,
    )


def _trace_is_complete(run: AccessRunResponse) -> bool:
    events = run.trace.events
    return (
        bool(events)
        and events[0].event_kind is AccessTraceKind.SELECT_MODE
        and events[-1].event_kind is AccessTraceKind.MODE_SUMMARY
        and events[-1].mode is run.resolved_mode
    )


def _fixed_lock_overridden(run: AccessRunResponse) -> bool:
    requested_mode = run.trace.requested_mode
    select_events = [
        event for event in run.trace.events if event.event_kind is AccessTraceKind.SELECT_MODE
    ]
    return (
        requested_mode is AccessMode.AUTO
        or run.resolved_mode is not requested_mode
        or len(select_events) != 1
        or select_events[0].mode is not requested_mode
    )


def _context(*, actor: str) -> PrimitiveExecutionContext:
    return PrimitiveExecutionContext(
        actor=actor,
        budget_scope_id=f"access::{actor}",
        budget_limit=None,
        capabilities=[Capability.MEMORY_READ],
    )
