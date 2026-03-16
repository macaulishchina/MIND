from __future__ import annotations

from functools import lru_cache

from mind.fixtures.golden_episode_set import build_golden_episode_set


@lru_cache(maxsize=4)
def episode_chunks(*, chunk_size: int) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return stable episode-id chunks for access-benchmark slicing."""

    episode_ids = tuple(episode.episode_id for episode in build_golden_episode_set())
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    return tuple(
        (
            f"episodes_{start // chunk_size + 1}",
            episode_ids[start : start + chunk_size],
        )
        for start in range(0, len(episode_ids), chunk_size)
    )
