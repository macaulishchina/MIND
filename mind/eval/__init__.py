"""Shared evaluation primitives for benchmark and strategy work."""

from .baselines import (
    FixedSummaryMemoryBaselineSystem,
    NoMemoryBaselineSystem,
    PlainRagBaselineSystem,
)
from .benchmark_gate import (
    BenchmarkComparisonResult,
    BenchmarkGateResult,
    ComparisonInterval,
    assert_benchmark_comparison,
    assert_benchmark_gate,
    evaluate_benchmark_comparison,
    evaluate_benchmark_gate,
    write_benchmark_comparison_report_json,
    write_benchmark_gate_report_json,
)
from .costing import (
    CostBudgetProfile,
    StrategyCostReport,
    evaluate_fixed_rule_cost_report,
    read_strategy_cost_report_json,
    write_strategy_cost_report_json,
)
from .mind_system import MindLongHorizonSystem, MindRunCostSnapshot
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
from .strategy_gate import (
    StrategyFamilyImprovement,
    StrategyGateResult,
    assert_strategy_gate,
    evaluate_strategy_gate,
    write_strategy_gate_report_json,
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
    "BenchmarkComparisonResult",
    "BenchmarkGateResult",
    "StrategyFamilyImprovement",
    "StrategyCostReport",
    "StrategyGateResult",
    "PlainRagBaselineSystem",
    "StrategyStepDecision",
    "assert_benchmark_comparison",
    "assert_benchmark_gate",
    "assert_strategy_gate",
    "build_benchmark_suite_report",
    "compute_pus",
    "evaluate_fixed_rule_cost_report",
    "evaluate_benchmark_comparison",
    "evaluate_benchmark_gate",
    "evaluate_strategy_gate",
    "read_benchmark_suite_report_json",
    "read_strategy_cost_report_json",
    "write_benchmark_suite_report_json",
    "write_benchmark_comparison_report_json",
    "write_benchmark_gate_report_json",
    "write_strategy_cost_report_json",
    "write_strategy_gate_report_json",
]
