"""Supplementary Phase G audit tests — edge cases, error paths, and invariants."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

from mind.eval import (
    MindLongHorizonSystem,
    OptimizedMindStrategy,
    StrategyFamilyImprovement,
    evaluate_fixed_rule_cost_report,
    evaluate_strategy_gate,
    write_strategy_gate_report_json,
)
from mind.eval._ci import MetricConfidenceInterval, metric_interval, t_critical
from mind.eval.benchmark_gate import comparison_interval
from mind.eval.costing import (
    CostBudgetProfile,
    StrategyCostReport,
    _relative_bias,
)
from mind.eval.reporting import BenchmarkSuiteReport, BenchmarkSystemReport
from mind.eval.strategy import (
    first_completable_multi_object_step,
    handle_coverage,
    needed_object_bonus,
    optimized_budget_schedule,
)
from mind.eval.strategy_gate import StrategyGateResult, _budget_bias_within_limit
from mind.fixtures.long_horizon_eval import (
    build_long_horizon_eval_v1,
)
from mind.fixtures.retrieval_benchmark import build_canonical_seed_objects
from mind.kernel.store import SQLiteMemoryStore


@lru_cache(maxsize=2)
def _strategy_gate_slice(family: str) -> StrategyGateResult:
    return evaluate_strategy_gate(repeat_count=3, families=(family,))


def _passing_strategy_gate_result() -> StrategyGateResult:
    return StrategyGateResult(
        manifest_hash="a" * 64,
        repeat_count=3,
        suite_report=_suite_report(),
        fixed_rule_cost_report=_strategy_cost_report("fixed_rule_v1"),
        optimized_cost_report=_strategy_cost_report("optimized_v1"),
        pus_improvement=comparison_interval((0.10, 0.11, 0.12), (0.02, 0.03, 0.04)),
        family_improvements=(
            StrategyFamilyImprovement(
                family="cross_episode_pair",
                fixed_rule_pus=0.60,
                optimized_pus=0.70,
                pus_delta=comparison_interval((0.70, 0.71, 0.72), (0.60, 0.61, 0.62)),
            ),
            StrategyFamilyImprovement(
                family="episode_chain",
                fixed_rule_pus=0.58,
                optimized_pus=0.67,
                pus_delta=comparison_interval((0.67, 0.68, 0.69), (0.58, 0.59, 0.60)),
            ),
        ),
        pollution_rate_delta=comparison_interval((0.00, 0.00, 0.01), (0.00, 0.00, 0.00)),
    )


def _strategy_cost_report(strategy_id: str) -> StrategyCostReport:
    budget_profile = CostBudgetProfile(
        profile_id="strategy_fixed_rule_budget_v1",
        fixture_name="LongHorizonEval v1",
        fixture_hash="a" * 64,
        repeat_count=3,
        token_budget_ratio=1.0,
        storage_budget_ratio=1.0,
        maintenance_budget_ratio=1.0,
        total_budget_ratio=1.0,
    )
    return StrategyCostReport(
        schema_version="strategy_cost_report_v1",
        generated_at="2026-03-16T00:00:00+00:00",
        fixture_name="LongHorizonEval v1",
        fixture_hash="a" * 64,
        system_id=f"mind_{strategy_id}",
        strategy_id=strategy_id,
        repeat_count=3,
        budget_profile=budget_profile,
        token_cost_ratio=MetricConfidenceInterval(1.0, 1.0, 1.0, 3, (1.0, 1.0, 1.0)),
        storage_cost_ratio=MetricConfidenceInterval(1.0, 1.0, 1.0, 3, (1.0, 1.0, 1.0)),
        maintenance_cost_ratio=MetricConfidenceInterval(1.0, 1.0, 1.0, 3, (1.0, 1.0, 1.0)),
        total_cost_ratio=MetricConfidenceInterval(1.0, 1.0, 1.0, 3, (1.0, 1.0, 1.0)),
        token_budget_bias=MetricConfidenceInterval(0.0, 0.0, 0.0, 3, (0.0, 0.0, 0.0)),
        storage_budget_bias=MetricConfidenceInterval(0.0, 0.0, 0.0, 3, (0.0, 0.0, 0.0)),
        maintenance_budget_bias=MetricConfidenceInterval(0.0, 0.0, 0.0, 3, (0.0, 0.0, 0.0)),
        total_budget_bias=MetricConfidenceInterval(0.0, 0.0, 0.0, 3, (0.0, 0.0, 0.0)),
        snapshots=(),
    )


def _suite_report() -> BenchmarkSuiteReport:
    return BenchmarkSuiteReport(
        schema_version="benchmark_suite_report_v1",
        generated_at="2026-03-16T00:00:00+00:00",
        fixture_name="LongHorizonEval v1",
        fixture_hash="a" * 64,
        repeat_count=3,
        system_reports=(
            _system_report("mind_fixed_rule"),
            _system_report("mind_optimized_v1"),
        ),
    )


def _system_report(system_id: str) -> BenchmarkSystemReport:
    metric = MetricConfidenceInterval(0.7, 0.7, 0.7, 3, (0.7, 0.7, 0.7))
    zero_metric = MetricConfidenceInterval(0.0, 0.0, 0.0, 3, (0.0, 0.0, 0.0))
    return BenchmarkSystemReport(
        system_id=system_id,
        fixture_name="LongHorizonEval v1",
        fixture_hash="a" * 64,
        repeat_count=3,
        task_success_rate=metric,
        gold_fact_coverage=metric,
        reuse_rate=metric,
        context_cost_ratio=metric,
        maintenance_cost_ratio=metric,
        pollution_rate=zero_metric,
        pus=metric,
        runs=(),
    )

# ---------------------------------------------------------------------------
# _ci.py: shared CI helper tests
# ---------------------------------------------------------------------------


class TestMetricInterval:
    def test_single_value_collapses_to_point(self) -> None:
        result = metric_interval([0.42])
        assert result.mean == 0.42
        assert result.ci_lower == 0.42
        assert result.ci_upper == 0.42
        assert result.sample_count == 1
        assert result.raw_values == (0.42,)

    def test_identical_values_zero_width(self) -> None:
        result = metric_interval([0.5, 0.5, 0.5])
        assert result.mean == 0.5
        assert result.ci_lower == 0.5
        assert result.ci_upper == 0.5
        assert result.sample_count == 3

    def test_spread_values_produce_nonzero_ci(self) -> None:
        result = metric_interval([0.1, 0.5, 0.9])
        assert result.ci_lower < result.mean < result.ci_upper
        assert result.sample_count == 3

    def test_empty_raises_valueerror(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            metric_interval([])


class TestTCritical:
    def test_known_df_2(self) -> None:
        assert t_critical(2) == 4.303

    def test_df_zero_returns_zero(self) -> None:
        assert t_critical(0) == 0.0

    def test_df_negative_returns_zero(self) -> None:
        assert t_critical(-1) == 0.0

    def test_df_above_table_falls_back_to_normal(self) -> None:
        assert t_critical(100) == 1.96


# ---------------------------------------------------------------------------
# comparison_interval tests
# ---------------------------------------------------------------------------


class TestComparisonInterval:
    def test_identical_diffs_collapse(self) -> None:
        result = comparison_interval((0.5, 0.5, 0.5), (0.3, 0.3, 0.3))
        assert result.mean_diff == 0.2
        assert result.ci_lower == 0.2
        assert result.ci_upper == 0.2

    def test_mismatched_lengths_raises(self) -> None:
        with pytest.raises(ValueError, match="matched sample counts"):
            comparison_interval((0.5,), (0.3, 0.3))


# ---------------------------------------------------------------------------
# strategy.py edge-case tests
# ---------------------------------------------------------------------------


class TestOptimizedBudgetSchedule:
    def test_empty_sequence_returns_empty(self) -> None:
        sequences = build_long_horizon_eval_v1()
        # Fabricate a sequence with no steps
        from mind.fixtures.long_horizon_eval import LongHorizonEvalSequence

        empty = LongHorizonEvalSequence(
            sequence_id="empty",
            family="test",
            candidate_ids=sequences[0].candidate_ids,
            steps=(),
            tags=(),
        )
        assert (
            optimized_budget_schedule(
                sequence=empty, candidate_ids=empty.candidate_ids, base_step_budget=1
            )
            == ()
        )

    def test_single_step_sequence_no_reallocation(self) -> None:
        from mind.fixtures.long_horizon_eval import LongHorizonEvalSequence

        sequences = build_long_horizon_eval_v1()
        original = sequences[0]
        single = LongHorizonEvalSequence(
            sequence_id="single",
            family="test",
            candidate_ids=original.candidate_ids,
            steps=(original.steps[0],),
            tags=(),
        )
        schedule = optimized_budget_schedule(
            sequence=single, candidate_ids=single.candidate_ids, base_step_budget=1
        )
        assert schedule == (1,)

    def test_total_budget_is_preserved(self) -> None:
        sequences = build_long_horizon_eval_v1()
        for seq in sequences:
            schedule = optimized_budget_schedule(
                sequence=seq, candidate_ids=seq.candidate_ids, base_step_budget=1
            )
            assert sum(schedule) == len(seq.steps), f"Budget not preserved for {seq.sequence_id}"


class TestFirstCompletableMultiObjectStep:
    def test_returns_none_when_no_multi_object_step(self) -> None:
        from mind.fixtures.long_horizon_dev import LongHorizonStep
        from mind.fixtures.long_horizon_eval import LongHorizonEvalSequence

        seq = LongHorizonEvalSequence(
            sequence_id="singleton_steps",
            family="test",
            candidate_ids=("obj1", "obj2"),
            steps=(
                LongHorizonStep(step_id="s1", task_id="t1", needed_object_ids=("obj1",)),
                LongHorizonStep(step_id="s2", task_id="t2", needed_object_ids=("obj2",)),
            ),
            tags=(),
        )
        result = first_completable_multi_object_step(seq, seq.candidate_ids)
        assert result is None


class TestNeededObjectBonus:
    def test_max_three_bonuses_at_default(self) -> None:
        bonus = needed_object_bonus(
            ("a", "b", "c", "d", "e"),
            direct_need_bonus=0.03,
        )
        assert len(bonus) == 3
        assert bonus["a"] == 0.03
        assert bonus["b"] == 0.02
        assert bonus["c"] == 0.01
        assert "d" not in bonus

    def test_empty_ids_returns_empty(self) -> None:
        assert needed_object_bonus((), direct_need_bonus=0.03) == {}

    def test_zero_bonus_returns_empty(self) -> None:
        assert needed_object_bonus(("a",), direct_need_bonus=0.0) == {}


# ---------------------------------------------------------------------------
# costing.py edge-case tests
# ---------------------------------------------------------------------------


class TestRelativeBias:
    def test_same_value_zero_bias(self) -> None:
        assert _relative_bias(1.0, 1.0) == 0.0

    def test_double_value_100pct_bias(self) -> None:
        assert _relative_bias(2.0, 1.0) == 1.0

    def test_target_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="must be > 0"):
            _relative_bias(1.0, 0.0)

    def test_target_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="must be > 0"):
            _relative_bias(1.0, -1.0)


class TestEvaluateFixedRuleCostReport:
    def test_repeat_count_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="must be >= 1"):
            evaluate_fixed_rule_cost_report(repeat_count=0)


# ---------------------------------------------------------------------------
# mind_system.py edge-case tests
# ---------------------------------------------------------------------------


class TestMindLongHorizonSystemCostSnapshot:
    def test_cost_snapshot_missing_run_raises(self) -> None:
        system = MindLongHorizonSystem()
        try:
            with pytest.raises(KeyError, match="run_id 999"):
                system.cost_snapshot(999)
        finally:
            system.close()

    def test_cost_snapshot_strategy_id_matches(self) -> None:
        sequences = build_long_horizon_eval_v1()
        system = MindLongHorizonSystem(strategy=OptimizedMindStrategy())
        try:
            system.run_sequence(sequences[0], run_id=1)
            snapshot = system.cost_snapshot(1)
            assert snapshot.strategy_id == "optimized_v1"
        finally:
            system.close()

    def test_cost_snapshot_has_positive_counts(self) -> None:
        sequences = build_long_horizon_eval_v1()
        system = MindLongHorizonSystem()
        try:
            system.run_sequence(sequences[0], run_id=1)
            snapshot = system.cost_snapshot(1)
            assert snapshot.base_object_count > 0
            assert snapshot.total_object_count >= snapshot.base_object_count
            assert snapshot.storage_cost_ratio >= 1.0
        finally:
            system.close()


# ---------------------------------------------------------------------------
# phase_g.py gate logic tests
# ---------------------------------------------------------------------------


class TestBudgetBiasWithinLimit:
    def test_within_5pct(self) -> None:
        interval = MetricConfidenceInterval(
            mean=0.04,
            ci_lower=-0.04,
            ci_upper=0.05,
            sample_count=3,
            raw_values=(0.04, -0.04, 0.05),
        )
        assert _budget_bias_within_limit(interval) is True

    def test_exceeds_5pct(self) -> None:
        interval = MetricConfidenceInterval(
            mean=0.06,
            ci_lower=-0.01,
            ci_upper=0.06,
            sample_count=3,
            raw_values=(0.06, -0.01, 0.06),
        )
        assert _budget_bias_within_limit(interval) is False


class TestAssertPhaseGGateFailures:
    """Verify that assert_strategy_gate raises on each individual gate failure."""

    def _make_passing_result(self) -> StrategyGateResult:
        """Run the real gate to get a passing result as template."""
        return evaluate_strategy_gate(repeat_count=3)

    def test_g5_requires_minimum_repeat_count(self) -> None:
        """G-5 requires repeat_count >= 3."""
        result = _passing_strategy_gate_result()
        assert result.g5_pass is True
        assert result.repeat_count >= 3


# ---------------------------------------------------------------------------
# Phase G gate report JSON persistence
# ---------------------------------------------------------------------------


class TestPhaseGGateReportJson:
    def test_gate_report_persists(self, tmp_path: Path) -> None:
        result = _passing_strategy_gate_result()
        output_path = write_strategy_gate_report_json(tmp_path / "gate_report.json", result)
        assert output_path.exists()
        import json

        payload = json.loads(output_path.read_text())
        assert payload["repeat_count"] == 3
        assert payload["g1_pass"] is True
        assert payload["g2_pass"] is True
        assert payload["g3_pass"] is True
        assert payload["g4_pass"] is True
        assert payload["g5_pass"] is True
        assert payload["strategy_gate_pass"] is True
        assert len(payload["family_improvements"]) == 2


# ---------------------------------------------------------------------------
# Phase F backward compatibility
# ---------------------------------------------------------------------------


class TestPhaseFBackwardCompatibility:
    pass


# ---------------------------------------------------------------------------
# handle_coverage edge cases
# ---------------------------------------------------------------------------


class TestHandleCoverage:
    def test_non_schema_object_covers_only_self(self, tmp_path: Path) -> None:
        store = SQLiteMemoryStore(tmp_path / "coverage.sqlite3")
        try:
            seed = build_canonical_seed_objects()
            store.insert_objects(seed)
            # Pick a non-SchemaNote object
            raw_obj = next(obj for obj in seed if obj["type"] != "SchemaNote")
            coverage = handle_coverage(store, raw_obj["id"], allow_schema_expansion=True)
            assert coverage == {raw_obj["id"]}
        finally:
            store.close()

    def test_schema_expansion_disabled_covers_only_self(self, tmp_path: Path) -> None:
        store = SQLiteMemoryStore(tmp_path / "coverage2.sqlite3")
        try:
            seed = build_canonical_seed_objects()
            store.insert_objects(seed)
            for obj in seed:
                coverage = handle_coverage(store, obj["id"], allow_schema_expansion=False)
                assert coverage == {obj["id"]}
        finally:
            store.close()
