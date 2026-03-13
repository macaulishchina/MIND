"""Closed-loop growth evaluation metrics (Phase α-4).

Provides three new metrics:

* ``GrowthLift`` — compares answer quality of A/B runs with and without
  offline maintenance.
* ``MemoryEfficiency`` — measures memory utility per stored object.
* ``FeedbackCorrelation`` — positive-feedback reuse rate vs negative-feedback
  reuse rate.

These metrics extend the existing ``LongHorizonBenchmarkRunner`` via
``GrowthLiftBenchmarkRunner``, an A/B wrapper.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mind.fixtures.long_horizon_eval import LongHorizonEvalSequence

from .runner import LongHorizonBenchmarkRun, LongHorizonSystemRunner


@dataclass(frozen=True)
class GrowthLiftResult:
    """A/B comparison showing the lift from offline maintenance."""

    with_maintenance_pus: float
    without_maintenance_pus: float
    growth_lift: float
    with_maintenance_task_success: float
    without_maintenance_task_success: float

    @classmethod
    def compute(
        cls,
        with_maintenance: LongHorizonBenchmarkRun,
        without_maintenance: LongHorizonBenchmarkRun,
    ) -> GrowthLiftResult:
        """Compute GrowthLift from two benchmark runs."""
        lift = round(with_maintenance.average_pus - without_maintenance.average_pus, 4)
        return cls(
            with_maintenance_pus=with_maintenance.average_pus,
            without_maintenance_pus=without_maintenance.average_pus,
            growth_lift=lift,
            with_maintenance_task_success=with_maintenance.average_task_success_rate,
            without_maintenance_task_success=without_maintenance.average_task_success_rate,
        )


@dataclass(frozen=True)
class MemoryEfficiencyResult:
    """Measures (quality * task_count) / total_objects for a benchmark run."""

    quality_score: float
    task_count: int
    total_objects: int
    memory_efficiency: float

    @classmethod
    def compute(
        cls,
        run: LongHorizonBenchmarkRun,
        total_objects: int,
    ) -> MemoryEfficiencyResult:
        """Compute MemoryEfficiency from a benchmark run and object count."""
        if total_objects <= 0:
            efficiency = 0.0
        else:
            task_count = run.sequence_count
            quality = run.average_task_success_rate
            efficiency = round((quality * task_count) / float(total_objects), 4)
        return cls(
            quality_score=run.average_task_success_rate,
            task_count=run.sequence_count,
            total_objects=total_objects,
            memory_efficiency=efficiency,
        )


@dataclass(frozen=True)
class FeedbackCorrelationResult:
    """Positive-feedback reuse rate vs negative-feedback reuse rate."""

    positive_reuse_rate: float
    negative_reuse_rate: float
    feedback_correlation: float

    @classmethod
    def compute(
        cls,
        *,
        positive_object_ids: set[str],
        negative_object_ids: set[str],
        selected_ids_per_step: list[list[str]],
    ) -> FeedbackCorrelationResult:
        """Compute FeedbackCorrelation over a sequence of retrieval steps.

        Args:
            positive_object_ids: IDs of objects that received positive feedback.
            negative_object_ids: IDs of objects that received negative feedback.
            selected_ids_per_step: Per-step lists of objects selected for context.
        """
        pos_hits = 0
        neg_hits = 0
        total_selections = sum(len(step) for step in selected_ids_per_step)
        if total_selections == 0:
            return cls(
                positive_reuse_rate=0.0,
                negative_reuse_rate=0.0,
                feedback_correlation=0.0,
            )
        for step_ids in selected_ids_per_step:
            for oid in step_ids:
                if oid in positive_object_ids:
                    pos_hits += 1
                if oid in negative_object_ids:
                    neg_hits += 1

        pos_rate = round(pos_hits / float(total_selections), 4) if positive_object_ids else 0.0
        neg_rate = round(neg_hits / float(total_selections), 4) if negative_object_ids else 0.0
        correlation = round(pos_rate - neg_rate, 4)
        return cls(
            positive_reuse_rate=pos_rate,
            negative_reuse_rate=neg_rate,
            feedback_correlation=correlation,
        )


@dataclass(frozen=True)
class GrowthPhaseAlphaReport:
    """Full Phase α closed-loop eval report."""

    growth_lift: GrowthLiftResult
    memory_efficiency: MemoryEfficiencyResult
    feedback_correlation: FeedbackCorrelationResult

    @property
    def alpha_gate_pass(self) -> bool:
        """Return True if the Phase α quality gates are met."""
        return (
            self.growth_lift.growth_lift >= 0.0
            and self.memory_efficiency.memory_efficiency >= 0.0
        )


class GrowthLiftBenchmarkRunner:
    """Run an A/B comparison for closed-loop growth measurement.

    Runs two systems against the same sequences:
    * ``system_with_maintenance``: the full MIND system with offline maintenance.
    * ``system_without_maintenance``: the same system without offline maintenance.

    Then computes GrowthLift, MemoryEfficiency, and FeedbackCorrelation.

    For accurate ``FeedbackCorrelation``, supply ``selected_ids_per_step`` to
    ``run()`` directly.  If omitted, the correlation metric will be empty since
    ``LongHorizonScoreCard`` aggregates step data and does not retain per-step
    selections.

    Usage::

        runner = GrowthLiftBenchmarkRunner(
            sequences=sequences,
            manifest=manifest,
            total_objects=total_objects,
        )
        report = runner.run(
            system_with_maintenance=mind_system,
            system_without_maintenance=baseline_system,
        )
        assert report.alpha_gate_pass
    """

    def __init__(
        self,
        *,
        sequences: list[LongHorizonEvalSequence],
        manifest: Any,
        total_objects: int = 0,
        positive_object_ids: set[str] | None = None,
        negative_object_ids: set[str] | None = None,
    ) -> None:
        from .runner import LongHorizonBenchmarkRunner

        self._runner = LongHorizonBenchmarkRunner(sequences=sequences, manifest=manifest)
        self._total_objects = total_objects
        self._positive_object_ids: set[str] = positive_object_ids or set()
        self._negative_object_ids: set[str] = negative_object_ids or set()

    def run(
        self,
        *,
        system_with_maintenance: LongHorizonSystemRunner,
        system_without_maintenance: LongHorizonSystemRunner,
        run_id: int = 1,
        selected_ids_per_step: list[list[str]] | None = None,
    ) -> GrowthPhaseAlphaReport:
        """Run both systems and compute Phase α growth metrics.

        Args:
            system_with_maintenance: The system that uses offline maintenance.
            system_without_maintenance: The baseline system without maintenance.
            run_id: Benchmark run identifier passed to each system.
            selected_ids_per_step: Optional list of per-step selected object ID
                lists from the ``with_maintenance`` run. When provided, enables
                accurate ``FeedbackCorrelation`` computation. When omitted, the
                correlation metric defaults to zero (no per-step data available).
        """
        run_with = self._runner.run_once(
            system_id="with_maintenance",
            system=system_with_maintenance,
            run_id=run_id,
        )
        run_without = self._runner.run_once(
            system_id="without_maintenance",
            system=system_without_maintenance,
            run_id=run_id,
        )
        growth_lift = GrowthLiftResult.compute(run_with, run_without)
        memory_efficiency = MemoryEfficiencyResult.compute(run_with, self._total_objects)
        effective_selected = (
            selected_ids_per_step
            if selected_ids_per_step is not None
            else _collect_selected_ids(run_with)
        )
        feedback_correlation = FeedbackCorrelationResult.compute(
            positive_object_ids=self._positive_object_ids,
            negative_object_ids=self._negative_object_ids,
            selected_ids_per_step=effective_selected,
        )
        return GrowthPhaseAlphaReport(
            growth_lift=growth_lift,
            memory_efficiency=memory_efficiency,
            feedback_correlation=feedback_correlation,
        )


def _collect_selected_ids(run: LongHorizonBenchmarkRun) -> list[list[str]]:
    """Extract per-step selected object IDs from a benchmark run.

    NOTE: ``LongHorizonScoreCard`` aggregates step data into summary metrics but
    does not retain per-step selections.  Callers that need accurate
    ``FeedbackCorrelation`` should supply ``selected_ids_per_step`` directly to
    ``GrowthLiftBenchmarkRunner`` rather than relying on this function.
    """
    return [[] for _ in run.sequence_results]


@dataclass(frozen=True)
class ArchiveReport:
    """Report summarising automatic archive activity (Phase γ-5).

    Attributes:
        archived_count: Number of objects archived in the observed window.
        unarchived_count: Number of objects restored (mis-archive corrections).
        total_objects: Total object count (archived + active) at evaluation time.
        archive_rate: Fraction of objects that were archived.
        misarchive_rate: Fraction of archived objects that were later restored.
    """

    archived_count: int
    unarchived_count: int
    total_objects: int
    archive_rate: float
    misarchive_rate: float

    @classmethod
    def compute(
        cls,
        *,
        archived_count: int,
        unarchived_count: int,
        total_objects: int,
    ) -> ArchiveReport:
        """Compute archive metrics from raw counts.

        Args:
            archived_count: Number of objects archived in the observed window.
            unarchived_count: Number of objects restored after auto-archiving.
            total_objects: Total object population (archived + active).
        """
        archive_rate = (
            round(archived_count / float(total_objects), 4)
            if total_objects > 0
            else 0.0
        )
        misarchive_rate = (
            round(unarchived_count / float(archived_count), 4)
            if archived_count > 0
            else 0.0
        )
        return cls(
            archived_count=archived_count,
            unarchived_count=unarchived_count,
            total_objects=total_objects,
            archive_rate=archive_rate,
            misarchive_rate=misarchive_rate,
        )

    @property
    def gamma_gate_pass(self) -> bool:
        """Return True when the archive quality gate is met.

        Gate: ``misarchive_rate <= 0.10`` (at most 10 % of archives are
        reversed, indicating the auto-archive heuristic is reliable).
        """
        return self.misarchive_rate <= 0.10
