from __future__ import annotations

from pathlib import Path

from mind.eval import (
    FixedRuleMindStrategy,
    MindLongHorizonSystem,
    PublicDatasetMindStrategy,
)
from mind.eval.strategy import optimized_budget_schedule, public_dataset_budget_schedule
from mind.fixtures.long_horizon_eval import build_long_horizon_eval_v1
from mind.fixtures.public_datasets.registry import build_public_dataset_long_horizon_sequences
from mind.fixtures.retrieval_benchmark import build_canonical_seed_objects
from mind.kernel.store import SQLiteMemoryStore
from mind.offline import select_replay_targets


def test_fixed_rule_strategy_returns_frozen_decision_shape(tmp_path: Path) -> None:
    db_path = tmp_path / "fixed_rule_strategy.sqlite3"
    store = SQLiteMemoryStore(db_path)
    try:
        store.insert_objects(build_canonical_seed_objects())
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


def test_public_dataset_strategy_preserves_final_reuse_budget_without_maintenance_targets() -> None:
    source_path = (
        Path(__file__).resolve().parent
        / "data"
        / "public_datasets"
        / "hotpotqa_local_slice.json"
    )
    sequences = build_public_dataset_long_horizon_sequences(
        "hotpotqa",
        source_path=source_path,
    )

    schedule = public_dataset_budget_schedule(sequence=sequences[0])

    assert schedule == (1, 1, 2, 0, 1)


def test_public_dataset_strategy_selects_non_empty_final_reuse_step(tmp_path: Path) -> None:
    db_path = tmp_path / "public_dataset_strategy.sqlite3"
    store = SQLiteMemoryStore(db_path)
    try:
        from mind.fixtures.public_datasets.registry import build_public_dataset_objects

        source_path = (
            Path(__file__).resolve().parent
            / "data"
            / "public_datasets"
            / "hotpotqa_local_slice.json"
        )
        store.insert_objects(build_public_dataset_objects("hotpotqa", source_path=source_path))
        sequence = build_public_dataset_long_horizon_sequences(
            "hotpotqa",
            source_path=source_path,
        )[0]
        ranking = select_replay_targets(
            store,
            sequence.candidate_ids,
            top_k=len(sequence.candidate_ids),
        )
        ranking_by_id = {target.object_id: target.score for target in ranking}

        final_step = sequence.steps[-1]
        decision = PublicDatasetMindStrategy().select_step_handles(
            store=store,
            sequence=sequence,
            step_index=len(sequence.steps) - 1,
            step=final_step,
            candidate_ids=sequence.candidate_ids,
            ranking_by_id=ranking_by_id,
        )

        assert decision.budget == 1
        assert decision.selected_ids
    finally:
        store.close()
