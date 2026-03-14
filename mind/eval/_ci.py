"""Shared confidence-interval helpers used by reporting and costing modules.

``MetricConfidenceInterval`` is defined here so that both ``reporting``
and ``costing`` can import it without circular dependencies.  ``reporting``
re-exports the dataclass for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, stdev

# ---------------------------------------------------------------------------
# Canonical MetricConfidenceInterval dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricConfidenceInterval:
    mean: float
    ci_lower: float
    ci_upper: float
    sample_count: int
    raw_values: tuple[float, ...]


# ---------------------------------------------------------------------------
# t-distribution critical values (two-tailed, 95 %)
# ---------------------------------------------------------------------------

T_CRITICAL_95: dict[int, float] = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.16,
    14: 2.145,
    15: 2.131,
    16: 2.12,
    17: 2.11,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.08,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.06,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}


def t_critical(degrees_of_freedom: int) -> float:
    """Return the two-tailed 95 % critical value for the given df."""

    if degrees_of_freedom <= 0:
        return 0.0
    if degrees_of_freedom in T_CRITICAL_95:
        return T_CRITICAL_95[degrees_of_freedom]
    return 1.96


def metric_interval(values: list[float]) -> MetricConfidenceInterval:
    """Build a ``MetricConfidenceInterval`` from a list of observations."""

    if not values:
        raise ValueError("metric interval requires at least one value")
    sample_count = len(values)
    center = round(mean(values), 4)
    if sample_count == 1:
        return MetricConfidenceInterval(
            mean=center,
            ci_lower=center,
            ci_upper=center,
            sample_count=sample_count,
            raw_values=tuple(round(value, 4) for value in values),
        )
    sample_std = stdev(values)
    margin = 0.0
    if sample_std != 0.0:
        margin = t_critical(sample_count - 1) * (sample_std / (sample_count**0.5))
    return MetricConfidenceInterval(
        mean=center,
        ci_lower=round(center - margin, 4),
        ci_upper=round(center + margin, 4),
        sample_count=sample_count,
        raw_values=tuple(round(value, 4) for value in values),
    )
