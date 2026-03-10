"""Supplementary Phase G audit tests — edge cases, error paths, and invariants."""

from __future__ import annotations

from pathlib import Path

import pytest

from mind.eval import (
    FixedRuleMindStrategy,
    LongHorizonBenchmarkRunner,
    MindLongHorizonSystem,
    OptimizedMindStrategy,
    evaluate_fixed_rule_cost_report,
    evaluate_phase_g_gate,
    write_phase_g_gate_report_json,
)
from mind.eval._ci import MetricConfidenceInterval, metric_interval, t_critical
from mind.eval.costing import (
    _relative_bias,
)
from mind.eval.phase_f import comparison_interval
from mind.eval.phase_g import PhaseGGateResult, _budget_bias_within_limit
from mind.eval.strategy import (
    first_completable_multi_object_step,
    handle_coverage,
    needed_object_bonus,
    optimized_budget_schedule,
)
from mind.fixtures.long_horizon_eval import (
    build_long_horizon_eval_manifest_v1,
    build_long_horizon_eval_v1,
)
from mind.fixtures.retrieval_benchmark import build_phase_d_seed_objects
from mind.kernel.store import SQLiteMemoryStore

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
        assert optimized_budget_schedule(
            sequence=empty, candidate_ids=empty.candidate_ids, base_step_budget=1
        ) == ()

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
            assert sum(schedule) == len(seq.steps), (
                f"Budget not preserved for {seq.sequence_id}"
            )


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
            mean=0.04, ci_lower=-0.04, ci_upper=0.05,
            sample_count=3, raw_values=(0.04, -0.04, 0.05),
        )
        assert _budget_bias_within_limit(interval) is True

    def test_exceeds_5pct(self) -> None:
        interval = MetricConfidenceInterval(
            mean=0.06, ci_lower=-0.01, ci_upper=0.06,
            sample_count=3, raw_values=(0.06, -0.01, 0.06),
        )
        assert _budget_bias_within_limit(interval) is False


class TestAssertPhaseGGateFailures:
    """Verify that assert_phase_g_gate raises on each individual gate failure."""

    def _make_passing_result(self) -> PhaseGGateResult:
        """Run the real gate to get a passing result as template."""
        return evaluate_phase_g_gate(repeat_count=3)

    def test_g5_requires_minimum_repeat_count(self) -> None:
        """G-5 requires repeat_count >= 3."""
        result = evaluate_phase_g_gate(repeat_count=3)
        assert result.g5_pass is True
        assert result.repeat_count >= 3


# ---------------------------------------------------------------------------
# Phase G gate report JSON persistence
# ---------------------------------------------------------------------------


class TestPhaseGGateReportJson:
    def test_gate_report_persists(self, tmp_path: Path) -> None:
        result = evaluate_phase_g_gate(repeat_count=3)
        output_path = write_phase_g_gate_report_json(
            tmp_path / "gate_report.json", result
        )
        assert output_path.exists()
        import json

        payload = json.loads(output_path.read_text())
        assert payload["phase_g_pass"] is True
        assert payload["g1_pass"] is True
        assert payload["g2_pass"] is True
        assert payload["g3_pass"] is True
        assert payload["g4_pass"] is True
        assert payload["g5_pass"] is True


# ---------------------------------------------------------------------------
# Phase F backward compatibility
# ---------------------------------------------------------------------------


class TestPhaseFBackwardCompatibility:
    def test_default_system_matches_explicit_fixed_rule_across_all_sequences(self) -> None:
        """Verify the refactored strategy injection doesn't regress Phase F behavior."""
        sequences = build_long_horizon_eval_v1()
        runner = LongHorizonBenchmarkRunner(
            sequences=sequences,
            manifest=build_long_horizon_eval_manifest_v1(),
        )
        default_system = MindLongHorizonSystem()
        explicit_system = MindLongHorizonSystem(strategy=FixedRuleMindStrategy())
        try:
            default_run = runner.run_once(
                system_id="mind_fixed_rule", system=default_system, run_id=1
            )
            explicit_run = runner.run_once(
                system_id="mind_fixed_rule", system=explicit_system, run_id=1
            )
        finally:
            default_system.close()
            explicit_system.close()

        assert default_run.average_pus == explicit_run.average_pus
        assert default_run.average_context_cost_ratio == explicit_run.average_context_cost_ratio
        assert (
            default_run.average_maintenance_cost_ratio
            == explicit_run.average_maintenance_cost_ratio
        )


# ---------------------------------------------------------------------------
# handle_coverage edge cases
# ---------------------------------------------------------------------------


class TestHandleCoverage:
    def test_non_schema_object_covers_only_self(self, tmp_path: Path) -> None:
        store = SQLiteMemoryStore(tmp_path / "coverage.sqlite3")
        try:
            seed = build_phase_d_seed_objects()
            store.insert_objects(seed)
            # Pick a non-SchemaNote object
            raw_obj = next(
                obj for obj in seed if obj["type"] != "SchemaNote"
            )
            coverage = handle_coverage(
                store, raw_obj["id"], allow_schema_expansion=True
            )
            assert coverage == {raw_obj["id"]}
        finally:
            store.close()

    def test_schema_expansion_disabled_covers_only_self(self, tmp_path: Path) -> None:
        store = SQLiteMemoryStore(tmp_path / "coverage2.sqlite3")
        try:
            seed = build_phase_d_seed_objects()
            store.insert_objects(seed)
            for obj in seed:
                coverage = handle_coverage(
                    store, obj["id"], allow_schema_expansion=False
                )
                assert coverage == {obj["id"]}
        finally:
            store.close()
