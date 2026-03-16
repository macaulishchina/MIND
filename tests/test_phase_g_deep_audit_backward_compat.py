from __future__ import annotations

import pytest

from mind.eval import FixedRuleMindStrategy, MindLongHorizonSystem
from tests._long_horizon_eval_support import family_sequence_chunks, subset_runner

_BACKWARD_COMPAT_CHUNKS = (
    family_sequence_chunks("episode_chain", chunk_size=5)
    + family_sequence_chunks("cross_episode_pair", chunk_size=5)
)


@pytest.mark.parametrize(
    ("chunk_name", "sequence_ids"),
    _BACKWARD_COMPAT_CHUNKS,
    ids=[chunk_name for chunk_name, _ in _BACKWARD_COMPAT_CHUNKS],
)
def test_default_system_matches_explicit_fixed_rule_for_each_sequence_chunk(
    chunk_name: str,
    sequence_ids: tuple[str, ...],
) -> None:
    assert chunk_name
    runner = subset_runner(sequence_ids)
    default_system = MindLongHorizonSystem()
    explicit_system = MindLongHorizonSystem(strategy=FixedRuleMindStrategy())
    try:
        default_run = runner.run_once(
            system_id="mind_fixed_rule",
            system=default_system,
            run_id=1,
        )
        explicit_run = runner.run_once(
            system_id="mind_fixed_rule",
            system=explicit_system,
            run_id=1,
        )
    finally:
        default_system.close()
        explicit_system.close()

    assert default_run.average_pus == explicit_run.average_pus
    assert default_run.average_context_cost_ratio == explicit_run.average_context_cost_ratio
    assert default_run.average_maintenance_cost_ratio == explicit_run.average_maintenance_cost_ratio
