"""LongHorizonDev v1 fixtures for Phase E replay / promotion evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from mind.fixtures.golden_episode_set import EpisodeFixture, build_golden_episode_set


@dataclass(frozen=True)
class LongHorizonStep:
    step_id: str
    task_id: str
    needed_object_ids: tuple[str, ...]


@dataclass(frozen=True)
class LongHorizonSequence:
    sequence_id: str
    candidate_ids: tuple[str, ...]
    steps: tuple[LongHorizonStep, ...]
    tags: tuple[str, ...]
    promotion_target_refs: tuple[str, ...] = ()


def build_long_horizon_dev_v1() -> list[LongHorizonSequence]:
    """Return the fixed LongHorizonDev v1 benchmark set."""

    episodes = build_golden_episode_set()
    failure_episodes = [
        episode
        for episode in episodes
        if any(obj["id"] == f"{episode.episode_id}-reflection" for obj in episode.objects)
    ]
    sequences = [_build_episode_sequence(index, episodes) for index in range(len(episodes))]
    sequences.extend(
        _build_failure_pair_sequence(index, left, right, episodes)
        for index, (left, right) in enumerate(
            combinations(failure_episodes, 2),
            start=len(sequences),
        )
    )

    if len(sequences) != 30:
        raise RuntimeError(f"LongHorizonDev v1 expected 30 sequences, got {len(sequences)}")
    if not all(5 <= len(sequence.steps) <= 10 for sequence in sequences):
        raise RuntimeError("LongHorizonDev v1 requires 5~10 steps per sequence")
    return sequences


def _build_episode_sequence(index: int, episodes: list[EpisodeFixture]) -> LongHorizonSequence:
    episode = episodes[index]
    neighbor = episodes[(index + 1) % len(episodes)]
    summary_id = f"{episode.episode_id}-summary"
    final_raw_id = _final_raw_id(episode)
    reflection_id = f"{episode.episode_id}-reflection"
    has_reflection = any(obj["id"] == reflection_id for obj in episode.objects)
    candidate_ids = [
        summary_id,
        episode.episode_id,
        final_raw_id,
        reflection_id if has_reflection else neighbor.episode_id,
        f"{neighbor.episode_id}-summary",
        _final_raw_id(neighbor),
        "showcase-summary",
        "showcase-episode",
        "showcase-schema",
        "showcase-entity",
    ]
    steps = [
        LongHorizonStep(
            step_id=f"{episode.episode_id}-step-01",
            task_id=episode.task_id,
            needed_object_ids=(summary_id,),
        ),
        LongHorizonStep(
            step_id=f"{episode.episode_id}-step-02",
            task_id=episode.task_id,
            needed_object_ids=(episode.episode_id,),
        ),
        LongHorizonStep(
            step_id=f"{episode.episode_id}-step-03",
            task_id=episode.task_id,
            needed_object_ids=(summary_id,),
        ),
        LongHorizonStep(
            step_id=f"{episode.episode_id}-step-04",
            task_id=episode.task_id,
            needed_object_ids=((reflection_id,) if has_reflection else (final_raw_id,)),
        ),
        LongHorizonStep(
            step_id=f"{episode.episode_id}-step-05",
            task_id=episode.task_id,
            needed_object_ids=(summary_id, final_raw_id),
        ),
    ]
    return LongHorizonSequence(
        sequence_id=f"long_horizon_episode_{episode.episode_id}",
        candidate_ids=tuple(candidate_ids),
        steps=tuple(steps),
        tags=("episode", "replay"),
    )


def _build_failure_pair_sequence(
    index: int,
    left: EpisodeFixture,
    right: EpisodeFixture,
    episodes: list[EpisodeFixture],
) -> LongHorizonSequence:
    success_anchor = episodes[index % len(episodes)]
    left_reflection = f"{left.episode_id}-reflection"
    right_reflection = f"{right.episode_id}-reflection"
    left_summary = f"{left.episode_id}-summary"
    right_summary = f"{right.episode_id}-summary"
    candidate_ids = (
        left_reflection,
        right_reflection,
        left_summary,
        right_summary,
        left.episode_id,
        right.episode_id,
        f"{success_anchor.episode_id}-summary",
        success_anchor.episode_id,
        "showcase-summary",
        "showcase-schema",
    )
    steps = (
        LongHorizonStep(
            step_id=f"{left.episode_id}_{right.episode_id}-step-01",
            task_id=left.task_id,
            needed_object_ids=(left_reflection,),
        ),
        LongHorizonStep(
            step_id=f"{left.episode_id}_{right.episode_id}-step-02",
            task_id=right.task_id,
            needed_object_ids=(right_reflection,),
        ),
        LongHorizonStep(
            step_id=f"{left.episode_id}_{right.episode_id}-step-03",
            task_id=f"{left.task_id}+{right.task_id}",
            needed_object_ids=(left_reflection, right_reflection),
        ),
        LongHorizonStep(
            step_id=f"{left.episode_id}_{right.episode_id}-step-04",
            task_id=f"{left.task_id}+{right.task_id}",
            needed_object_ids=(left_reflection, right_reflection),
        ),
        LongHorizonStep(
            step_id=f"{left.episode_id}_{right.episode_id}-step-05",
            task_id=f"{left.task_id}+{right.task_id}",
            needed_object_ids=(left_reflection, right_reflection),
        ),
    )
    return LongHorizonSequence(
        sequence_id=f"long_horizon_failure_pair_{left.episode_id}_{right.episode_id}",
        candidate_ids=candidate_ids,
        steps=steps,
        tags=("failure_pair", "replay", "promotion"),
        promotion_target_refs=(left_reflection, right_reflection),
    )


def _final_raw_id(episode: EpisodeFixture) -> str:
    raw_records = [obj for obj in episode.objects if obj["type"] == "RawRecord"]
    final_raw = max(raw_records, key=lambda obj: int(obj["metadata"]["timestamp_order"]))
    return str(final_raw["id"])
