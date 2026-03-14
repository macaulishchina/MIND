from __future__ import annotations

from collections import Counter
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from mind.access import (
    AccessBenchmarkResult,
    AccessMode,
    AccessTaskFamily,
    evaluate_access_benchmark,
)
from mind.access import benchmark as access_benchmark


@lru_cache(maxsize=1)
def _benchmark_result() -> AccessBenchmarkResult:
    return evaluate_access_benchmark()


def test_access_benchmark_runs_all_modes_across_all_cases() -> None:
    result = _benchmark_result()

    assert result.case_count == 60
    assert result.run_count == 300
    assert Counter(run.requested_mode for run in result.runs) == {
        AccessMode.FLASH: 60,
        AccessMode.RECALL: 60,
        AccessMode.RECONSTRUCT: 60,
        AccessMode.REFLECTIVE_ACCESS: 60,
        AccessMode.AUTO: 60,
    }
    assert len(result.mode_family_aggregates) == 15
    assert len(result.frontier_comparisons) == 3


def test_access_benchmark_frontier_comparison_uses_expected_fixed_families() -> None:
    result = _benchmark_result()
    comparison_by_family = {
        comparison.task_family: comparison for comparison in result.frontier_comparisons
    }

    assert (
        comparison_by_family[AccessTaskFamily.SPEED_SENSITIVE].family_best_fixed_mode
        is AccessMode.FLASH
    )
    assert (
        comparison_by_family[AccessTaskFamily.BALANCED].family_best_fixed_mode is AccessMode.RECALL
    )
    assert comparison_by_family[AccessTaskFamily.HIGH_CORRECTNESS].family_best_fixed_mode in {
        AccessMode.RECONSTRUCT,
        AccessMode.REFLECTIVE_ACCESS,
    }


def test_access_benchmark_auto_aggregates_exist_for_all_task_families() -> None:
    result = _benchmark_result()
    auto_aggregates = {
        aggregate.task_family: aggregate
        for aggregate in result.mode_family_aggregates
        if aggregate.requested_mode is AccessMode.AUTO
    }

    assert set(auto_aggregates) == {
        AccessTaskFamily.SPEED_SENSITIVE,
        AccessTaskFamily.BALANCED,
        AccessTaskFamily.HIGH_CORRECTNESS,
    }
    assert all(
        0.0 <= aggregate.cost_efficiency_score <= 1.0 for aggregate in auto_aggregates.values()
    )
    assert all(
        0.0 <= aggregate.answer_quality_score <= 1.0 for aggregate in auto_aggregates.values()
    )


def test_access_benchmark_reuses_per_case_baseline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cases = [
        SimpleNamespace(case_id="case-1"),
        SimpleNamespace(case_id="case-2"),
    ]
    baseline_calls: list[str] = []
    baselines: dict[str, access_benchmark._BaselineExecution] = {}

    class FakeStore:
        def __enter__(self) -> FakeStore:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            del exc_type, exc, tb

        def insert_objects(self, objects: Any) -> None:
            self.objects = tuple(objects)

    class FakeAccessService:
        def __init__(self, store: FakeStore) -> None:
            self.store = store

    class FakePrimitiveService:
        def __init__(self, store: FakeStore) -> None:
            self.store = store

    def fake_baseline(
        case: SimpleNamespace,
        primitive_service: FakePrimitiveService,
        store: FakeStore,
    ) -> access_benchmark._BaselineExecution:
        del primitive_service, store
        baseline_calls.append(case.case_id)
        baseline = access_benchmark._BaselineExecution(
            context_token_count=1,
            answer_token_count=1,
            read_count=1,
            estimated_latency_ms=1,
        )
        baselines[case.case_id] = baseline
        return baseline

    def fake_evaluate_case(
        *,
        case: SimpleNamespace,
        requested_mode: AccessMode,
        access_service: FakeAccessService,
        baseline: access_benchmark._BaselineExecution,
    ) -> access_benchmark.AccessBenchmarkRun:
        assert baseline is baselines[case.case_id]
        assert isinstance(access_service, FakeAccessService)
        return access_benchmark.AccessBenchmarkRun(
            case_id=case.case_id,
            requested_mode=requested_mode,
            resolved_mode=requested_mode,
            task_family=AccessTaskFamily.BALANCED,
            context_kind=access_benchmark.AccessContextKind.RAW_TOPK,
            answer_text="answer",
            support_ids=(),
            candidate_ids=(),
            context_object_ids=(),
            read_object_ids=(),
            expanded_object_ids=(),
            selected_object_ids=(),
            task_completion_score=1.0,
            constraint_satisfaction=1.0,
            gold_fact_coverage=1.0,
            answer_faithfulness=1.0,
            answer_quality_score=1.0,
            needed_memory_recall_at_20=1.0,
            workspace_support_precision=1.0,
            answer_trace_support=1.0,
            memory_use_score=1.0,
            estimated_latency_ms=1,
            time_budget_hit=True,
            context_cost_ratio=1.0,
            generation_token_ratio=1.0,
            read_count_ratio=1.0,
            latency_ratio=1.0,
            online_cost_ratio=1.0,
            cost_efficiency_score=1.0,
        )

    monkeypatch.setattr(access_benchmark, "build_access_depth_bench_v1", lambda: cases)
    monkeypatch.setattr(access_benchmark, "build_canonical_seed_objects", lambda: ())
    monkeypatch.setattr(access_benchmark, "AccessService", FakeAccessService)
    monkeypatch.setattr(access_benchmark, "PrimitiveService", FakePrimitiveService)
    monkeypatch.setattr(access_benchmark, "_baseline_execution", fake_baseline)
    monkeypatch.setattr(access_benchmark, "_evaluate_case", fake_evaluate_case)
    monkeypatch.setattr(access_benchmark, "_aggregate_runs", lambda runs: ())
    monkeypatch.setattr(access_benchmark, "_build_frontier_comparisons", lambda aggregates: ())

    result = access_benchmark.evaluate_access_benchmark(
        db_path=tmp_path / "benchmark.sqlite3",
        store_factory=cast(Any, lambda _path: FakeStore()),
    )

    assert baseline_calls == ["case-1", "case-2"]
    assert result.case_count == 2
    assert result.run_count == 10
