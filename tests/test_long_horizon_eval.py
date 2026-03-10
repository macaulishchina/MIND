from __future__ import annotations

from mind.fixtures.long_horizon_dev import build_long_horizon_dev_v1
from mind.fixtures.long_horizon_eval import (
    build_long_horizon_eval_manifest_v1,
    build_long_horizon_eval_v1,
)


def test_long_horizon_eval_v1_is_frozen_and_separate_from_dev() -> None:
    eval_sequences = build_long_horizon_eval_v1()
    dev_sequences = build_long_horizon_dev_v1()

    assert len(eval_sequences) == 50
    assert all(5 <= len(sequence.steps) <= 10 for sequence in eval_sequences)
    assert {sequence.sequence_id for sequence in eval_sequences}.isdisjoint(
        {sequence.sequence_id for sequence in dev_sequences}
    )
    assert {len(sequence.steps) for sequence in eval_sequences} == {6}


def test_long_horizon_eval_manifest_v1_has_stable_shape() -> None:
    manifest = build_long_horizon_eval_manifest_v1()

    assert manifest.fixture_name == "LongHorizonEval v1"
    assert len(manifest.fixture_hash) == 64
    assert manifest.sequence_count == 50
    assert manifest.min_step_count == 6
    assert manifest.max_step_count == 6
    assert manifest.family_counts == (("cross_episode_pair", 30), ("episode_chain", 20))
