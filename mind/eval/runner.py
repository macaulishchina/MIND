"""Benchmark runner skeleton for LongHorizonEval-based evaluation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import mean
from typing import Protocol

from mind.fixtures.long_horizon_eval import LongHorizonEvalManifest, LongHorizonEvalSequence


@dataclass(frozen=True)
class LongHorizonScoreCard:
    task_success_rate: float
    gold_fact_coverage: float
    reuse_rate: float
    context_cost_ratio: float
    maintenance_cost_ratio: float
    pollution_rate: float

    @property
    def pus(self) -> float:
        return compute_pus(
            task_success_rate=self.task_success_rate,
            gold_fact_coverage=self.gold_fact_coverage,
            reuse_rate=self.reuse_rate,
            context_cost_ratio=self.context_cost_ratio,
            maintenance_cost_ratio=self.maintenance_cost_ratio,
            pollution_rate=self.pollution_rate,
        )


@dataclass(frozen=True)
class LongHorizonEvalSequenceResult:
    sequence_id: str
    family: str
    score_card: LongHorizonScoreCard


@dataclass(frozen=True)
class LongHorizonBenchmarkRun:
    system_id: str
    run_id: int
    fixture_name: str
    fixture_hash: str
    sequence_count: int
    average_task_success_rate: float
    average_gold_fact_coverage: float
    average_reuse_rate: float
    average_context_cost_ratio: float
    average_maintenance_cost_ratio: float
    average_pollution_rate: float
    average_pus: float
    sequence_results: tuple[LongHorizonEvalSequenceResult, ...]


class LongHorizonSystemRunner(Protocol):
    """Protocol implemented by systems participating in benchmark runs."""

    def run_sequence(
        self,
        sequence: LongHorizonEvalSequence,
        *,
        run_id: int,
    ) -> LongHorizonScoreCard: ...


class LongHorizonBenchmarkRunner:
    """Run one or more systems against a frozen LongHorizonEval manifest."""

    def __init__(
        self,
        *,
        sequences: Sequence[LongHorizonEvalSequence],
        manifest: LongHorizonEvalManifest,
    ) -> None:
        if len(sequences) != manifest.sequence_count:
            raise ValueError(
                "sequence count does not match manifest "
                f"({len(sequences)} != {manifest.sequence_count})"
            )
        self._sequences = tuple(sequences)
        self._manifest = manifest

    def run_once(
        self,
        *,
        system_id: str,
        system: LongHorizonSystemRunner,
        run_id: int = 1,
    ) -> LongHorizonBenchmarkRun:
        sequence_results = tuple(
            LongHorizonEvalSequenceResult(
                sequence_id=sequence.sequence_id,
                family=sequence.family,
                score_card=system.run_sequence(sequence, run_id=run_id),
            )
            for sequence in self._sequences
        )
        return LongHorizonBenchmarkRun(
            system_id=system_id,
            run_id=run_id,
            fixture_name=self._manifest.fixture_name,
            fixture_hash=self._manifest.fixture_hash,
            sequence_count=len(sequence_results),
            average_task_success_rate=round(
                mean(result.score_card.task_success_rate for result in sequence_results),
                4,
            ),
            average_gold_fact_coverage=round(
                mean(result.score_card.gold_fact_coverage for result in sequence_results),
                4,
            ),
            average_reuse_rate=round(
                mean(result.score_card.reuse_rate for result in sequence_results),
                4,
            ),
            average_context_cost_ratio=round(
                mean(result.score_card.context_cost_ratio for result in sequence_results),
                4,
            ),
            average_maintenance_cost_ratio=round(
                mean(result.score_card.maintenance_cost_ratio for result in sequence_results),
                4,
            ),
            average_pollution_rate=round(
                mean(result.score_card.pollution_rate for result in sequence_results),
                4,
            ),
            average_pus=round(mean(result.score_card.pus for result in sequence_results), 4),
            sequence_results=sequence_results,
        )

    def run_many(
        self,
        *,
        system_id: str,
        system: LongHorizonSystemRunner,
        repeat_count: int,
    ) -> tuple[LongHorizonBenchmarkRun, ...]:
        if repeat_count < 1:
            raise ValueError("repeat_count must be >= 1")
        return tuple(
            self.run_once(system_id=system_id, system=system, run_id=run_id)
            for run_id in range(1, repeat_count + 1)
        )


def compute_pus(
    *,
    task_success_rate: float,
    gold_fact_coverage: float,
    reuse_rate: float,
    context_cost_ratio: float,
    maintenance_cost_ratio: float,
    pollution_rate: float,
) -> float:
    """Compute the frozen PUS score used by gate logic."""

    _validate_ratio("task_success_rate", task_success_rate)
    _validate_ratio("gold_fact_coverage", gold_fact_coverage)
    _validate_ratio("reuse_rate", reuse_rate)
    _validate_ratio("pollution_rate", pollution_rate)
    if context_cost_ratio < 0.0:
        raise ValueError("context_cost_ratio must be >= 0")
    if maintenance_cost_ratio < 0.0:
        raise ValueError("maintenance_cost_ratio must be >= 0")
    return round(
        (
            0.55 * task_success_rate
            + 0.15 * gold_fact_coverage
            + 0.10 * reuse_rate
            - 0.10 * context_cost_ratio
            - 0.05 * maintenance_cost_ratio
            - 0.05 * pollution_rate
        ),
        4,
    )


def _validate_ratio(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be within [0, 1], got {value}")
