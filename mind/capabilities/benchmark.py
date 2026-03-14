"""CapabilityAdapterBench v1 runner."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from .adapter import CapabilityAdapter
from .config import resolve_capability_provider_config
from .contracts import CapabilityName, CapabilityProviderFamily
from .service import CapabilityService, CapabilityServiceError

if TYPE_CHECKING:
    from mind.fixtures.capability_adapter_bench import CapabilityAdapterScenario


@dataclass(frozen=True)
class CapabilityBenchCaseResult:
    scenario_id: str
    capability: CapabilityName
    provider_family: CapabilityProviderFamily
    expected_response_type: str
    response_type: str | None
    passed: bool
    fallback_used: bool
    error_message: str | None


@dataclass(frozen=True)
class CapabilityBenchmarkResult:
    case_count: int
    passed_case_count: int
    failed_case_count: int
    case_results: tuple[CapabilityBenchCaseResult, ...]

    @property
    def pass_rate(self) -> float:
        if self.case_count == 0:
            return 1.0
        return round(self.passed_case_count / float(self.case_count), 4)


def evaluate_capability_adapter_bench(
    scenarios: Iterable[CapabilityAdapterScenario] | None = None,
    *,
    adapters: list[CapabilityAdapter] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> CapabilityBenchmarkResult:
    """Run CapabilityAdapterBench v1 against the configured adapters."""

    scenario_list = tuple(scenarios or _default_scenarios())
    case_results = tuple(
        _run_benchmark_case(scenario, adapters=adapters, clock=clock) for scenario in scenario_list
    )
    passed_case_count = sum(case.passed for case in case_results)
    return CapabilityBenchmarkResult(
        case_count=len(case_results),
        passed_case_count=passed_case_count,
        failed_case_count=len(case_results) - passed_case_count,
        case_results=case_results,
    )


def assert_capability_adapter_bench(
    result: CapabilityBenchmarkResult,
    *,
    min_pass_rate: float = 0.95,
) -> None:
    if result.pass_rate >= min_pass_rate:
        return
    raise RuntimeError(
        "K-7 failed: "
        f"pass_rate={result.pass_rate:.4f} < {min_pass_rate:.4f} "
        f"({result.passed_case_count}/{result.case_count})"
    )


def _run_benchmark_case(
    scenario: CapabilityAdapterScenario,
    *,
    adapters: list[CapabilityAdapter] | None,
    clock: Callable[[], datetime] | None,
) -> CapabilityBenchCaseResult:
    service = CapabilityService(
        provider_config=resolve_capability_provider_config(
            env={"MIND_PROVIDER": scenario.provider_family.value}
        ),
        adapters=adapters,
        clock=clock,
    )
    try:
        response = service.invoke(scenario.request)
    except CapabilityServiceError as exc:
        return CapabilityBenchCaseResult(
            scenario_id=scenario.scenario_id,
            capability=scenario.capability,
            provider_family=scenario.provider_family,
            expected_response_type=scenario.expected_response_type.__name__,
            response_type=None,
            passed=False,
            fallback_used=False,
            error_message=str(exc),
        )

    return CapabilityBenchCaseResult(
        scenario_id=scenario.scenario_id,
        capability=scenario.capability,
        provider_family=scenario.provider_family,
        expected_response_type=scenario.expected_response_type.__name__,
        response_type=type(response).__name__,
        passed=isinstance(response, scenario.expected_response_type),
        fallback_used=response.trace.fallback_used,
        error_message=None,
    )


def _default_scenarios() -> tuple[CapabilityAdapterScenario, ...]:
    from mind.fixtures.capability_adapter_bench import build_capability_adapter_bench_v1

    return build_capability_adapter_bench_v1()
