from __future__ import annotations

from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from mind.access import AccessBenchmarkResult, AccessMode, AccessTaskFamily
from mind.access import benchmark as access_benchmark
from mind.access.benchmark import AccessBenchmarkRun, merge_access_benchmark_results


def test_access_benchmark_merge_reassembles_disjoint_results() -> None:
    left = AccessBenchmarkResult(
        case_count=1,
        run_count=1,
        runs=(_run(case_id="speed-1", task_family=AccessTaskFamily.SPEED_SENSITIVE),),
        mode_family_aggregates=(),
        frontier_comparisons=(),
    )
    right = AccessBenchmarkResult(
        case_count=1,
        run_count=1,
        runs=(_run(case_id="balanced-1", task_family=AccessTaskFamily.BALANCED),),
        mode_family_aggregates=(),
        frontier_comparisons=(),
    )

    merged = merge_access_benchmark_results((left, right))

    assert merged.case_count == 2
    assert merged.run_count == 2
    assert {run.case_id for run in merged.runs} == {"speed-1", "balanced-1"}
    assert len(merged.mode_family_aggregates) == 2
    assert len(merged.frontier_comparisons) == 0


def test_access_benchmark_merge_preserves_unique_case_count_across_mode_slices() -> None:
    speed_flash = AccessBenchmarkResult(
        case_count=1,
        run_count=1,
        runs=(
            _run(
                case_id="speed-1",
                task_family=AccessTaskFamily.SPEED_SENSITIVE,
                mode=AccessMode.FLASH,
            ),
        ),
        mode_family_aggregates=(),
        frontier_comparisons=(),
    )
    speed_auto = AccessBenchmarkResult(
        case_count=1,
        run_count=1,
        runs=(
            _run(
                case_id="speed-1",
                task_family=AccessTaskFamily.SPEED_SENSITIVE,
                mode=AccessMode.AUTO,
            ),
        ),
        mode_family_aggregates=(),
        frontier_comparisons=(),
    )

    merged = merge_access_benchmark_results((speed_flash, speed_auto))

    assert merged.case_count == 1
    assert merged.run_count == 2
    assert Counter(run.requested_mode for run in merged.runs) == {
        AccessMode.FLASH: 1,
        AccessMode.AUTO: 1,
    }
    assert len(merged.mode_family_aggregates) == 2
    assert len(merged.frontier_comparisons) == 1


def test_access_benchmark_reuses_per_case_baseline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cases = [
        SimpleNamespace(case_id="case-1", task_family=AccessTaskFamily.BALANCED),
        SimpleNamespace(case_id="case-2", task_family=AccessTaskFamily.BALANCED),
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
        return _run(
            case_id=case.case_id,
            task_family=AccessTaskFamily.BALANCED,
            mode=requested_mode,
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


def test_access_benchmark_default_modes_include_all_runtime_modes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cases = [SimpleNamespace(case_id="case-1", task_family=AccessTaskFamily.BALANCED)]
    requested_modes: list[AccessMode] = []

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

    def fake_evaluate_case(
        *,
        case: SimpleNamespace,
        requested_mode: AccessMode,
        access_service: object,
        baseline: object,
    ) -> access_benchmark.AccessBenchmarkRun:
        del access_service, baseline
        requested_modes.append(requested_mode)
        return _run(case_id=case.case_id, task_family=case.task_family, mode=requested_mode)

    monkeypatch.setattr(access_benchmark, "build_access_depth_bench_v1", lambda: cases)
    monkeypatch.setattr(access_benchmark, "build_canonical_seed_objects", lambda: ())
    monkeypatch.setattr(access_benchmark, "AccessService", FakeAccessService)
    monkeypatch.setattr(access_benchmark, "PrimitiveService", FakePrimitiveService)
    monkeypatch.setattr(
        access_benchmark,
        "_baseline_execution",
        lambda case, primitive_service, store: access_benchmark._BaselineExecution(
            context_token_count=1,
            answer_token_count=1,
            read_count=1,
            estimated_latency_ms=1,
        ),
    )
    monkeypatch.setattr(
        access_benchmark,
        "_evaluate_case",
        fake_evaluate_case,
    )
    monkeypatch.setattr(access_benchmark, "_aggregate_runs", lambda runs: ())
    monkeypatch.setattr(access_benchmark, "_build_frontier_comparisons", lambda aggregates: ())

    access_benchmark.evaluate_access_benchmark(
        db_path=tmp_path / "benchmark.sqlite3",
        store_factory=cast(Any, lambda _path: FakeStore()),
    )

    assert requested_modes == [
        AccessMode.FLASH,
        AccessMode.RECALL,
        AccessMode.RECONSTRUCT,
        AccessMode.REFLECTIVE_ACCESS,
        AccessMode.AUTO,
    ]


def _run(
    *,
    case_id: str,
    task_family: AccessTaskFamily,
    mode: AccessMode = AccessMode.AUTO,
) -> AccessBenchmarkRun:
    return access_benchmark.AccessBenchmarkRun(
        case_id=case_id,
        requested_mode=mode,
        resolved_mode=mode,
        task_family=task_family,
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
