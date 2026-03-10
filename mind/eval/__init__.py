"""Shared evaluation primitives for Phase F and later benchmark work."""

from .baselines import (
    FixedSummaryMemoryBaselineSystem,
    NoMemoryBaselineSystem,
    PlainRagBaselineSystem,
)
from .costing import (
    CostBudgetProfile,
    PhaseGCostReport,
    evaluate_fixed_rule_cost_report,
    read_phase_g_cost_report_json,
    write_phase_g_cost_report_json,
)
from .mind_system import MindLongHorizonSystem, MindRunCostSnapshot
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
from .phase_g import (
    PhaseGFamilyImprovement,
    PhaseGGateResult,
    assert_phase_g_gate,
    evaluate_phase_g_gate,
    write_phase_g_gate_report_json,
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
from .strategy import (
    FixedRuleMindStrategy,
    MindStrategy,
    OptimizedMindStrategy,
    StrategyStepDecision,
)

__all__ = [
    "BenchmarkSuiteReport",
    "BenchmarkSystemReport",
    "ComparisonInterval",
    "CostBudgetProfile",
    "FixedSummaryMemoryBaselineSystem",
    "FixedRuleMindStrategy",
    "LongHorizonBenchmarkRun",
    "LongHorizonBenchmarkRunner",
    "LongHorizonEvalSequenceResult",
    "LongHorizonScoreCard",
    "LongHorizonSystemRunner",
    "MetricConfidenceInterval",
    "MindLongHorizonSystem",
    "MindRunCostSnapshot",
    "MindStrategy",
    "NoMemoryBaselineSystem",
    "OptimizedMindStrategy",
    "PhaseFComparisonResult",
    "PhaseFGateResult",
    "PhaseGFamilyImprovement",
    "PhaseGCostReport",
    "PhaseGGateResult",
    "PlainRagBaselineSystem",
    "StrategyStepDecision",
    "assert_phase_f_comparison",
    "assert_phase_f_gate",
    "assert_phase_g_gate",
    "build_benchmark_suite_report",
    "compute_pus",
    "evaluate_fixed_rule_cost_report",
    "evaluate_phase_f_comparison",
    "evaluate_phase_f_gate",
    "evaluate_phase_g_gate",
    "read_benchmark_suite_report_json",
    "read_phase_g_cost_report_json",
    "write_benchmark_suite_report_json",
    "write_phase_f_comparison_report_json",
    "write_phase_f_gate_report_json",
    "write_phase_g_cost_report_json",
    "write_phase_g_gate_report_json",
]
