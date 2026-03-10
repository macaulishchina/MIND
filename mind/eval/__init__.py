"""Shared evaluation primitives for Phase F and later benchmark work."""

from .baselines import (
    FixedSummaryMemoryBaselineSystem,
    NoMemoryBaselineSystem,
    PlainRagBaselineSystem,
)
from .mind_system import MindLongHorizonSystem
from .phase_f import (
    ComparisonInterval,
    PhaseFComparisonResult,
    PhaseFGateResult,
    assert_phase_f_comparison,
    assert_phase_f_gate,
    evaluate_phase_f_comparison,
    evaluate_phase_f_gate,
    write_phase_f_comparison_report_json,
    write_phase_f_gate_report_json,
)
from .reporting import (
    BenchmarkSuiteReport,
    BenchmarkSystemReport,
    MetricConfidenceInterval,
    build_benchmark_suite_report,
    read_benchmark_suite_report_json,
    write_benchmark_suite_report_json,
)
from .runner import (
    LongHorizonBenchmarkRun,
    LongHorizonBenchmarkRunner,
    LongHorizonEvalSequenceResult,
    LongHorizonScoreCard,
    LongHorizonSystemRunner,
    compute_pus,
)

__all__ = [
    "BenchmarkSuiteReport",
    "BenchmarkSystemReport",
    "ComparisonInterval",
    "FixedSummaryMemoryBaselineSystem",
    "LongHorizonBenchmarkRun",
    "LongHorizonBenchmarkRunner",
    "LongHorizonEvalSequenceResult",
    "LongHorizonScoreCard",
    "LongHorizonSystemRunner",
    "MetricConfidenceInterval",
    "MindLongHorizonSystem",
    "NoMemoryBaselineSystem",
    "PhaseFComparisonResult",
    "PhaseFGateResult",
    "PlainRagBaselineSystem",
    "assert_phase_f_comparison",
    "assert_phase_f_gate",
    "build_benchmark_suite_report",
    "compute_pus",
    "evaluate_phase_f_comparison",
    "evaluate_phase_f_gate",
    "read_benchmark_suite_report_json",
    "write_benchmark_suite_report_json",
    "write_phase_f_comparison_report_json",
    "write_phase_f_gate_report_json",
]
