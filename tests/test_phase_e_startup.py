from __future__ import annotations

from pathlib import Path

from mind.fixtures.long_horizon_dev import build_long_horizon_dev_v1
from mind.offline import assert_offline_startup, evaluate_offline_startup


def test_long_horizon_dev_v1_is_frozen_at_30_sequences() -> None:
    sequences = build_long_horizon_dev_v1()

    assert len(sequences) == 30
    assert all(5 <= len(sequence.steps) <= 10 for sequence in sequences)
    assert sum("promotion" in sequence.tags for sequence in sequences) == 10


def test_phase_e_startup_baseline_passes(tmp_path: Path) -> None:
    result = evaluate_offline_startup(tmp_path / "phase_e.sqlite3")

    assert_offline_startup(result)
    assert result.sequence_count == 30
    assert result.min_step_count == 5
    assert result.max_step_count == 5
    assert result.promotion_sequence_count == 10
    assert result.audited_schema_count == 10
    assert result.replay_lift >= 1.5
    assert result.schema_validation_precision >= 0.85
    assert result.promotion_precision_at_10 >= 0.80
    assert result.top_decile_reuse_rate > result.random_decile_reuse_rate
