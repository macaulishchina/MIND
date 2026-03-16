from __future__ import annotations

import pytest

from mind.eval import FixedRuleMindStrategy, MindLongHorizonSystem, OptimizedMindStrategy
from tests._long_horizon_eval_support import family_sequence_chunks, subset_runner

_STRATEGY_CHUNKS = (
    family_sequence_chunks("episode_chain", chunk_size=5)
    + family_sequence_chunks("cross_episode_pair", chunk_size=5)
)


@pytest.mark.parametrize(
    ("chunk_name", "sequence_ids"),
    _STRATEGY_CHUNKS,
    ids=[chunk_name for chunk_name, _ in _STRATEGY_CHUNKS],
)
def test_optimized_strategy_improves_each_benchmark_chunk_without_budget_drift(
    chunk_name: str,
    sequence_ids: tuple[str, ...],
) -> None:
    assert chunk_name
    runner = subset_runner(sequence_ids)
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
