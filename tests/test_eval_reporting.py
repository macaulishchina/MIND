from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mind.eval import (
    FixedSummaryMemoryBaselineSystem,
    LongHorizonBenchmarkRunner,
    NoMemoryBaselineSystem,
    PlainRagBaselineSystem,
    build_benchmark_suite_report,
    read_benchmark_suite_report_json,
    write_benchmark_suite_report_json,
)
from mind.fixtures.long_horizon_eval import (
    build_long_horizon_eval_manifest_v1,
    build_long_horizon_eval_v1,
)


def test_benchmark_suite_report_persists_and_round_trips(tmp_path: Path) -> None:
    runner = LongHorizonBenchmarkRunner(
        sequences=build_long_horizon_eval_v1(),
        manifest=build_long_horizon_eval_manifest_v1(),
    )
    runs_by_system = {
        "fixed_summary_memory": runner.run_many(
            system_id="fixed_summary_memory",
            system=FixedSummaryMemoryBaselineSystem(),
            repeat_count=3,
        ),
        "no_memory": runner.run_many(
            system_id="no_memory",
            system=NoMemoryBaselineSystem(),
            repeat_count=3,
        ),
        "plain_rag": runner.run_many(
            system_id="plain_rag",
            system=PlainRagBaselineSystem(),
            repeat_count=3,
        ),
    }

    report = build_benchmark_suite_report(
        runs_by_system=runs_by_system,
        generated_at=datetime(2026, 3, 9, 23, 0, tzinfo=UTC),
    )

    assert report.schema_version == "phase_f_benchmark_report_v1"
    assert report.fixture_name == "LongHorizonEval v1"
    assert report.repeat_count == 3
    assert tuple(system.system_id for system in report.system_reports) == (
        "fixed_summary_memory",
        "no_memory",
        "plain_rag",
    )

    output_path = write_benchmark_suite_report_json(tmp_path / "phase_f_report.json", report)
    reloaded = read_benchmark_suite_report_json(output_path)

    assert reloaded == report


def test_benchmark_suite_report_exposes_ci_metrics() -> None:
    runner = LongHorizonBenchmarkRunner(
        sequences=build_long_horizon_eval_v1(),
        manifest=build_long_horizon_eval_manifest_v1(),
    )
    report = build_benchmark_suite_report(
        runs_by_system={
            "no_memory": runner.run_many(
                system_id="no_memory",
                system=NoMemoryBaselineSystem(),
                repeat_count=3,
            ),
            "plain_rag": runner.run_many(
                system_id="plain_rag",
                system=PlainRagBaselineSystem(),
                repeat_count=3,
            ),
        }
    )

    no_memory = next(system for system in report.system_reports if system.system_id == "no_memory")
    plain_rag = next(system for system in report.system_reports if system.system_id == "plain_rag")

    assert no_memory.pus.sample_count == 3
    assert no_memory.pus.mean == -0.05
    assert no_memory.pus.ci_lower == -0.05
    assert no_memory.pus.ci_upper == -0.05
    assert plain_rag.pus.sample_count == 3
    assert plain_rag.pus.mean == 0.1375
    assert plain_rag.pus.ci_lower <= plain_rag.pus.mean <= plain_rag.pus.ci_upper
