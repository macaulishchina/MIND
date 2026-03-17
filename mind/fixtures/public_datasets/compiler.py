"""Compiler helpers for public dataset benchmark adapters."""

from __future__ import annotations

import hashlib
import json
from collections import Counter

from mind.fixtures.episode_answer_bench import EpisodeAnswerBenchCase
from mind.fixtures.long_horizon_dev import LongHorizonStep
from mind.fixtures.long_horizon_eval import LongHorizonEvalManifest, LongHorizonEvalSequence
from mind.fixtures.public_datasets.contracts import (
    NormalizedEpisodeBundle,
    NormalizedLongHorizonSequenceSpec,
    PublicDatasetFixture,
)
from mind.fixtures.retrieval_benchmark import RetrievalBenchmarkCase


def compile_retrieval_cases(fixture: PublicDatasetFixture) -> list[RetrievalBenchmarkCase]:
    """Compile retrieval benchmark cases for one public dataset fixture."""

    cases: list[RetrievalBenchmarkCase] = []
    for bundle in fixture.bundles:
        for spec in bundle.retrieval_specs:
            cases.append(
                RetrievalBenchmarkCase(
                    case_id=_benchmark_case_id(fixture, bundle, spec.case_key),
                    task_id=bundle.task_id,
                    query=spec.query,
                    query_modes=spec.query_modes,
                    filters=dict(spec.filters),
                    gold_candidate_ids=spec.gold_candidate_ids,
                    gold_fact_ids=spec.gold_fact_ids,
                    slot_limit=spec.slot_limit,
                    vector_scores=spec.vector_scores,
                )
            )
    return cases


def compile_answer_cases(fixture: PublicDatasetFixture) -> list[EpisodeAnswerBenchCase]:
    """Compile answer benchmark cases for one public dataset fixture."""

    cases: list[EpisodeAnswerBenchCase] = []
    for bundle in fixture.bundles:
        for spec in bundle.answer_specs:
            cases.append(
                EpisodeAnswerBenchCase(
                    case_id=_benchmark_case_id(fixture, bundle, spec.case_key),
                    task_id=bundle.task_id,
                    episode_id=bundle.episode_id,
                    prompt=spec.prompt,
                    answer_kind=spec.answer_kind,
                    required_fragments=spec.required_fragments,
                    gold_fact_ids=spec.gold_fact_ids,
                    gold_memory_refs=spec.gold_memory_refs,
                    max_answer_tokens=spec.max_answer_tokens,
                )
            )
    return cases


def compile_long_horizon_sequences(fixture: PublicDatasetFixture) -> list[LongHorizonEvalSequence]:
    """Compile long-horizon benchmark sequences for one public dataset fixture."""

    return [_compile_long_horizon_sequence(fixture, spec) for spec in fixture.sequence_specs]


def build_long_horizon_manifest(fixture: PublicDatasetFixture) -> LongHorizonEvalManifest:
    """Build a deterministic long-horizon manifest for one public dataset fixture."""

    sequences = compile_long_horizon_sequences(fixture)
    family_counts = Counter(sequence.family for sequence in sequences)
    step_counts = [len(sequence.steps) for sequence in sequences]
    payload = {
        "fixture_name": fixture.fixture_name(),
        "sequences": [_serialize_sequence(sequence) for sequence in sequences],
    }
    fixture_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return LongHorizonEvalManifest(
        fixture_name=fixture.fixture_name(),
        fixture_hash=fixture_hash,
        sequence_count=len(sequences),
        min_step_count=min(step_counts) if step_counts else 0,
        max_step_count=max(step_counts) if step_counts else 0,
        family_counts=tuple(sorted(family_counts.items())),
    )


def compile_objects(fixture: PublicDatasetFixture) -> list[dict[str, object]]:
    """Return the flattened object corpus for one public dataset fixture."""

    objects: list[dict[str, object]] = []
    for bundle in fixture.bundles:
        objects.extend(bundle.objects)
    return objects


def _compile_long_horizon_sequence(
    fixture: PublicDatasetFixture,
    spec: NormalizedLongHorizonSequenceSpec,
) -> LongHorizonEvalSequence:
    steps = tuple(
        LongHorizonStep(
            step_id=f"{fixture.descriptor.dataset_name}_{spec.sequence_key}_{step.step_key}",
            task_id=step.task_id,
            needed_object_ids=step.needed_object_ids,
        )
        for step in spec.steps
    )
    return LongHorizonEvalSequence(
        sequence_id=f"{fixture.descriptor.dataset_name}_{spec.sequence_key}",
        family=spec.family,
        candidate_ids=spec.candidate_ids,
        steps=steps,
        tags=spec.tags,
        maintenance_target_refs=spec.maintenance_target_refs,
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


def _benchmark_case_id(
    fixture: PublicDatasetFixture,
    bundle: NormalizedEpisodeBundle,
    case_key: str,
) -> str:
    return f"{fixture.descriptor.dataset_name}_{bundle.episode_id}_{case_key}"
