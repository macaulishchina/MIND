from __future__ import annotations

from pathlib import Path

from mind.eval import (
    FixedRuleMindStrategy,
    LongHorizonBenchmarkRunner,
    MindLongHorizonSystem,
    OptimizedMindStrategy,
)
from mind.eval.strategy import optimized_budget_schedule
from mind.fixtures.long_horizon_eval import (
    build_long_horizon_eval_manifest_v1,
    build_long_horizon_eval_v1,
)
from mind.fixtures.retrieval_benchmark import build_phase_d_seed_objects
from mind.kernel.store import SQLiteMemoryStore
from mind.offline import select_replay_targets


def test_fixed_rule_strategy_returns_frozen_decision_shape(tmp_path: Path) -> None:
    db_path = tmp_path / "fixed_rule_strategy.sqlite3"
    store = SQLiteMemoryStore(db_path)
    try:
        store.insert_objects(build_phase_d_seed_objects())
        sequence = build_long_horizon_eval_v1()[0]
        step = sequence.steps[0]
        ranking = select_replay_targets(
            store,
            sequence.candidate_ids,
            top_k=len(sequence.candidate_ids),
        )
        ranking_by_id = {target.object_id: target.score for target in ranking}

        decision = FixedRuleMindStrategy().select_step_handles(
            store=store,
            sequence=sequence,
            step_index=0,
            step=step,
            candidate_ids=sequence.candidate_ids,
            ranking_by_id=ranking_by_id,
        )

        assert decision.budget == 1
        assert decision.prefer_future_coverage is True
        assert decision.allow_schema_expansion is True
        assert len(decision.selected_ids) <= decision.budget
        assert all(object_id in sequence.candidate_ids for object_id in decision.selected_ids)
    finally:
        store.close()


def test_explicit_fixed_rule_strategy_matches_default_mind_system() -> None:
    sequence = build_long_horizon_eval_v1()[0]
    default_system = MindLongHorizonSystem()
    explicit_system = MindLongHorizonSystem(strategy=FixedRuleMindStrategy())

    try:
        default_score = default_system.run_sequence(sequence, run_id=1)
        explicit_score = explicit_system.run_sequence(sequence, run_id=1)
    finally:
        default_system.close()
        explicit_system.close()

    assert explicit_score == default_score


def test_optimized_strategy_reallocates_budget_to_high_value_step() -> None:
    sequences = build_long_horizon_eval_v1()

    episode_chain_schedule = optimized_budget_schedule(
        sequence=sequences[0],
        candidate_ids=sequences[0].candidate_ids,
        base_step_budget=1,
    )
    cross_episode_schedule = optimized_budget_schedule(
        sequence=sequences[20],
        candidate_ids=sequences[20].candidate_ids,
        base_step_budget=1,
    )

    assert episode_chain_schedule == (1, 1, 1, 1, 2, 0)
    assert cross_episode_schedule == (1, 1, 2, 1, 1, 0)


def test_optimized_strategy_improves_single_run_without_budget_drift() -> None:
    runner = LongHorizonBenchmarkRunner(
        sequences=build_long_horizon_eval_v1(),
        manifest=build_long_horizon_eval_manifest_v1(),
    )
    fixed_system = MindLongHorizonSystem(strategy=FixedRuleMindStrategy())
    optimized_system = MindLongHorizonSystem(strategy=OptimizedMindStrategy())

    try:
        fixed_run = runner.run_once(system_id="mind_fixed_rule", system=fixed_system, run_id=1)
        optimized_run = runner.run_once(
            system_id="mind_optimized_v1",
            system=optimized_system,
            run_id=1,
        )
        fixed_snapshot = fixed_system.cost_snapshot(1)
        optimized_snapshot = optimized_system.cost_snapshot(1)
    finally:
        fixed_system.close()
        optimized_system.close()

    assert optimized_run.average_pus >= round(fixed_run.average_pus + 0.05, 4)
    assert optimized_run.average_context_cost_ratio == fixed_run.average_context_cost_ratio
    assert optimized_run.average_maintenance_cost_ratio == fixed_run.average_maintenance_cost_ratio
    assert optimized_snapshot.storage_cost_ratio == fixed_snapshot.storage_cost_ratio
