from __future__ import annotations

from dataclasses import dataclass

from mind.eval import LongHorizonBenchmarkRunner, LongHorizonScoreCard
from mind.fixtures.long_horizon_eval import (
    LongHorizonEvalSequence,
    build_long_horizon_eval_manifest_v1,
    build_long_horizon_eval_v1,
)


@dataclass
class DummySystem:
    def run_sequence(
        self,
        sequence: LongHorizonEvalSequence,
        *,
        run_id: int,
    ) -> LongHorizonScoreCard:
        if sequence.family == "episode_chain":
            return LongHorizonScoreCard(
                task_success_rate=1.0,
                gold_fact_coverage=0.9,
                reuse_rate=0.8,
                context_cost_ratio=0.4,
                maintenance_cost_ratio=0.1 * run_id,
                pollution_rate=0.0,
            )
        return LongHorizonScoreCard(
            task_success_rate=0.8,
            gold_fact_coverage=0.7,
            reuse_rate=0.6,
            context_cost_ratio=0.5,
            maintenance_cost_ratio=0.1 * run_id,
            pollution_rate=0.0,
        )


def test_benchmark_runner_aggregates_sequence_scores() -> None:
    runner = LongHorizonBenchmarkRunner(
        sequences=build_long_horizon_eval_v1(),
        manifest=build_long_horizon_eval_manifest_v1(),
    )

    result = runner.run_once(system_id="dummy", system=DummySystem(), run_id=2)

    assert result.system_id == "dummy"
    assert result.run_id == 2
    assert result.fixture_name == "LongHorizonEval v1"
    assert result.sequence_count == 50
    assert result.average_task_success_rate == 0.88
    assert result.average_gold_fact_coverage == 0.78
    assert result.average_reuse_rate == 0.68
    assert result.average_context_cost_ratio == 0.46
    assert result.average_maintenance_cost_ratio == 0.2
    assert result.average_pollution_rate == 0.0
    assert result.average_pus == 0.613


def test_benchmark_runner_run_many_requires_positive_repeat_count() -> None:
    runner = LongHorizonBenchmarkRunner(
        sequences=build_long_horizon_eval_v1(),
        manifest=build_long_horizon_eval_manifest_v1(),
    )

    runs = runner.run_many(system_id="dummy", system=DummySystem(), repeat_count=3)

    assert tuple(run.run_id for run in runs) == (1, 2, 3)
