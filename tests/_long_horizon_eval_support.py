from __future__ import annotations

from collections import Counter
from functools import lru_cache

from mind.eval import LongHorizonBenchmarkRunner
from mind.fixtures.long_horizon_eval import (
    build_long_horizon_eval_manifest_v1,
    build_long_horizon_eval_v1,
)


@lru_cache(maxsize=4)
def family_sequence_ids(family: str) -> tuple[str, ...]:
    """Return the stable ordered sequence ids for one long-horizon family."""

    return tuple(
        sequence.sequence_id
        for sequence in build_long_horizon_eval_v1()
        if sequence.family == family
    )


@lru_cache(maxsize=8)
def family_sequence_chunks(
    family: str,
    *,
    chunk_size: int,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Split one family into stable file-friendly benchmark chunks."""

    sequence_ids = family_sequence_ids(family)
    if not sequence_ids:
        raise ValueError(f"unknown family: {family}")
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    return tuple(
        (
            f"{family}_{start // chunk_size + 1}",
            sequence_ids[start : start + chunk_size],
        )
        for start in range(0, len(sequence_ids), chunk_size)
    )


def subset_runner(sequence_ids: tuple[str, ...]) -> LongHorizonBenchmarkRunner:
    """Build a benchmark runner for one stable subset of sequence ids."""

    manifest = build_long_horizon_eval_manifest_v1()
    sequence_id_set = set(sequence_ids)
    sequences = tuple(
        sequence
        for sequence in build_long_horizon_eval_v1()
        if sequence.sequence_id in sequence_id_set
    )
    if not sequences:
        raise ValueError("sequence_ids filter removed all benchmark sequences")
    family_counts = Counter(sequence.family for sequence in sequences)
    filtered_manifest = type(manifest)(
        fixture_name=manifest.fixture_name,
        fixture_hash=manifest.fixture_hash,
        sequence_count=len(sequences),
        min_step_count=min(len(sequence.steps) for sequence in sequences),
        max_step_count=max(len(sequence.steps) for sequence in sequences),
        family_counts=tuple(sorted(family_counts.items())),
    )
    return LongHorizonBenchmarkRunner(sequences=sequences, manifest=filtered_manifest)
