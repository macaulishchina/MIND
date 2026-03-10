"""LongHorizonEval v1 fixtures and manifest helpers for benchmark evaluation."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from itertools import combinations, islice

from mind.fixtures.golden_episode_set import EpisodeFixture, build_golden_episode_set
from mind.fixtures.long_horizon_dev import LongHorizonStep


@dataclass(frozen=True)
class LongHorizonEvalSequence:
    sequence_id: str
    family: str
    candidate_ids: tuple[str, ...]
    steps: tuple[LongHorizonStep, ...]
    tags: tuple[str, ...]
    maintenance_target_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class LongHorizonEvalManifest:
    fixture_name: str
    fixture_hash: str
    sequence_count: int
    min_step_count: int
    max_step_count: int
    family_counts: tuple[tuple[str, int], ...]


def build_long_horizon_eval_v1() -> list[LongHorizonEvalSequence]:
    """Return the fixed LongHorizonEval v1 benchmark set."""

    episodes = build_golden_episode_set()
    sequences = [_build_episode_chain_sequence(index, episodes) for index in range(len(episodes))]
    pair_sequences = [
        _build_cross_episode_pair_sequence(index, left, right, episodes)
        for index, (left, right) in enumerate(
            islice(combinations(episodes, 2), 30),
            start=len(sequences),
        )
    ]
    sequences.extend(pair_sequences)

    if len(sequences) != 50:
        raise RuntimeError(f"LongHorizonEval v1 expected 50 sequences, got {len(sequences)}")
    if not all(5 <= len(sequence.steps) <= 10 for sequence in sequences):
        raise RuntimeError("LongHorizonEval v1 requires 5~10 steps per sequence")
    return sequences


def build_long_horizon_eval_manifest_v1() -> LongHorizonEvalManifest:
    """Return the frozen manifest for LongHorizonEval v1."""

    sequences = build_long_horizon_eval_v1()
    family_counts = Counter(sequence.family for sequence in sequences)
    step_counts = [len(sequence.steps) for sequence in sequences]
    payload = {
        "fixture_name": "LongHorizonEval v1",
        "sequences": [_serialize_sequence(sequence) for sequence in sequences],
    }
    fixture_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return LongHorizonEvalManifest(
        fixture_name="LongHorizonEval v1",
        fixture_hash=fixture_hash,
        sequence_count=len(sequences),
        min_step_count=min(step_counts),
        max_step_count=max(step_counts),
        family_counts=tuple(sorted(family_counts.items())),
    )


def _build_episode_chain_sequence(
    index: int,
    episodes: list[EpisodeFixture],
) -> LongHorizonEvalSequence:
    episode = episodes[index]
    previous_episode = episodes[(index - 1) % len(episodes)]
    next_episode = episodes[(index + 1) % len(episodes)]
    summary_id = f"{episode.episode_id}-summary"
    previous_summary_id = f"{previous_episode.episode_id}-summary"
    next_summary_id = f"{next_episode.episode_id}-summary"
    final_raw_id = _final_raw_id(episode)
    reflection_id = f"{episode.episode_id}-reflection"
    has_reflection = any(obj["id"] == reflection_id for obj in episode.objects)
    candidate_ids = (
        summary_id,
        episode.episode_id,
        final_raw_id,
        previous_summary_id,
        next_summary_id,
        previous_episode.episode_id,
        next_episode.episode_id,
        reflection_id if has_reflection else f"{previous_episode.episode_id}-summary",
        "showcase-summary",
        "showcase-schema",
    )
    steps = (
        LongHorizonStep(
            step_id=f"{episode.episode_id}-eval-step-01",
            task_id=episode.task_id,
            needed_object_ids=(summary_id,),
        ),
        LongHorizonStep(
            step_id=f"{episode.episode_id}-eval-step-02",
            task_id=episode.task_id,
            needed_object_ids=(episode.episode_id,),
        ),
        LongHorizonStep(
            step_id=f"{episode.episode_id}-eval-step-03",
            task_id=episode.task_id,
            needed_object_ids=(next_summary_id,),
        ),
        LongHorizonStep(
            step_id=f"{episode.episode_id}-eval-step-04",
            task_id=episode.task_id,
            needed_object_ids=((reflection_id,) if has_reflection else (final_raw_id,)),
        ),
        LongHorizonStep(
            step_id=f"{episode.episode_id}-eval-step-05",
            task_id=episode.task_id,
            needed_object_ids=(summary_id, final_raw_id),
        ),
        LongHorizonStep(
            step_id=f"{episode.episode_id}-eval-step-06",
            task_id=f"{episode.task_id}+{next_episode.task_id}",
            needed_object_ids=(episode.episode_id, next_summary_id),
        ),
    )
    maintenance_target_refs = (reflection_id,) if has_reflection else ()
    return LongHorizonEvalSequence(
        sequence_id=f"long_horizon_eval_episode_{episode.episode_id}",
        family="episode_chain",
        candidate_ids=candidate_ids,
        steps=steps,
        tags=("eval", "episode_chain"),
        maintenance_target_refs=maintenance_target_refs,
    )


def _build_cross_episode_pair_sequence(
    index: int,
    left: EpisodeFixture,
    right: EpisodeFixture,
    episodes: list[EpisodeFixture],
) -> LongHorizonEvalSequence:
    anchor = episodes[(index + 3) % len(episodes)]
    left_summary = f"{left.episode_id}-summary"
    right_summary = f"{right.episode_id}-summary"
    left_reflection = f"{left.episode_id}-reflection"
    right_reflection = f"{right.episode_id}-reflection"
    left_reflection_available = any(obj["id"] == left_reflection for obj in left.objects)
    right_reflection_available = any(obj["id"] == right_reflection for obj in right.objects)
    left_fallback = _final_raw_id(left)
    right_fallback = _final_raw_id(right)
    candidate_ids = (
        left_summary,
        right_summary,
        left.episode_id,
        right.episode_id,
        left_reflection if left_reflection_available else left_fallback,
        right_reflection if right_reflection_available else right_fallback,
        f"{anchor.episode_id}-summary",
        anchor.episode_id,
        "showcase-summary",
        "showcase-schema",
    )
    steps = (
        LongHorizonStep(
            step_id=f"{left.episode_id}_{right.episode_id}-eval-step-01",
            task_id=left.task_id,
            needed_object_ids=(left_summary,),
        ),
        LongHorizonStep(
            step_id=f"{left.episode_id}_{right.episode_id}-eval-step-02",
            task_id=right.task_id,
            needed_object_ids=(right_summary,),
        ),
        LongHorizonStep(
            step_id=f"{left.episode_id}_{right.episode_id}-eval-step-03",
            task_id=f"{left.task_id}+{right.task_id}",
            needed_object_ids=(left.episode_id, right.episode_id),
        ),
        LongHorizonStep(
            step_id=f"{left.episode_id}_{right.episode_id}-eval-step-04",
            task_id=f"{left.task_id}+{right.task_id}",
            needed_object_ids=(
                left_reflection if left_reflection_available else left_fallback,
                right_reflection if right_reflection_available else right_fallback,
            ),
        ),
        LongHorizonStep(
            step_id=f"{left.episode_id}_{right.episode_id}-eval-step-05",
            task_id=f"{left.task_id}+{right.task_id}",
            needed_object_ids=(left_summary, right_summary),
        ),
        LongHorizonStep(
            step_id=f"{left.episode_id}_{right.episode_id}-eval-step-06",
            task_id=f"{left.task_id}+{right.task_id}+{anchor.task_id}",
            needed_object_ids=(left.episode_id, f"{anchor.episode_id}-summary"),
        ),
    )
    maintenance_targets = tuple(
        ref
        for ref, available in (
            (left_reflection, left_reflection_available),
            (right_reflection, right_reflection_available),
        )
        if available
    )
    return LongHorizonEvalSequence(
        sequence_id=f"long_horizon_eval_pair_{left.episode_id}_{right.episode_id}",
        family="cross_episode_pair",
        candidate_ids=candidate_ids,
        steps=steps,
        tags=("eval", "cross_episode_pair"),
        maintenance_target_refs=maintenance_targets,
    )


def _serialize_sequence(sequence: LongHorizonEvalSequence) -> dict[str, object]:
    return {
        "sequence_id": sequence.sequence_id,
        "family": sequence.family,
        "candidate_ids": list(sequence.candidate_ids),
        "steps": [
            {
                "step_id": step.step_id,
                "task_id": step.task_id,
                "needed_object_ids": list(step.needed_object_ids),
            }
            for step in sequence.steps
        ],
        "tags": list(sequence.tags),
        "maintenance_target_refs": list(sequence.maintenance_target_refs),
    }


def _final_raw_id(episode: EpisodeFixture) -> str:
    raw_records = [obj for obj in episode.objects if obj["type"] == "RawRecord"]
    final_raw = max(raw_records, key=lambda obj: int(obj["metadata"]["timestamp_order"]))
    return str(final_raw["id"])
