from __future__ import annotations

from mind.eval import (
    FixedSummaryMemoryBaselineSystem,
    LongHorizonBenchmarkRunner,
    NoMemoryBaselineSystem,
    PlainRagBaselineSystem,
)
from mind.fixtures.long_horizon_eval import (
    build_long_horizon_eval_manifest_v1,
    build_long_horizon_eval_v1,
)


def test_phase_f_baselines_are_runnable_and_ordered() -> None:
    runner = LongHorizonBenchmarkRunner(
        sequences=build_long_horizon_eval_v1(),
        manifest=build_long_horizon_eval_manifest_v1(),
    )

    no_memory = runner.run_once(system_id="no_memory", system=NoMemoryBaselineSystem())
    fixed_summary = runner.run_once(
        system_id="fixed_summary_memory",
        system=FixedSummaryMemoryBaselineSystem(),
    )
    plain_rag = runner.run_once(system_id="plain_rag", system=PlainRagBaselineSystem())

    assert no_memory.average_task_success_rate == 0.0
    assert no_memory.average_gold_fact_coverage == 0.0
    assert no_memory.average_pus == -0.05
    assert fixed_summary.average_task_success_rate > no_memory.average_task_success_rate
    assert fixed_summary.average_gold_fact_coverage > no_memory.average_gold_fact_coverage
    assert fixed_summary.average_pus > no_memory.average_pus
    assert plain_rag.average_task_success_rate > no_memory.average_task_success_rate
    assert plain_rag.average_gold_fact_coverage > no_memory.average_gold_fact_coverage
    assert plain_rag.average_pus > no_memory.average_pus
