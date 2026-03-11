"""Phase K failure and trace audit helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from .adapter import CapabilityAdapter
from .config import resolve_capability_provider_config
from .contracts import (
    CapabilityFallbackPolicy,
    CapabilityInvocationTrace,
    CapabilityName,
    CapabilityProviderFamily,
)
from .service import CapabilityService, CapabilityServiceError

if TYPE_CHECKING:
    from mind.fixtures.capability_adapter_bench import CapabilityAdapterScenario


@dataclass(frozen=True)
class CapabilityAuditCaseResult:
    scenario_id: str
    capability: CapabilityName
    requested_provider_family: CapabilityProviderFamily
    fallback_policy: CapabilityFallbackPolicy
    outcome: str
    fallback_used: bool
    trace_complete: bool
    trace_provider_family: CapabilityProviderFamily | None
    error_message: str | None


@dataclass(frozen=True)
class CapabilityFailureAuditResult:
    audited_case_count: int
    fallback_success_count: int
    structured_failure_count: int
    unexpected_failure_count: int
    silent_drift_count: int
    case_results: tuple[CapabilityAuditCaseResult, ...]

    @property
    def pass_rate(self) -> float:
        if self.audited_case_count == 0:
            return 1.0
        return round(
            (self.fallback_success_count + self.structured_failure_count)
            / float(self.audited_case_count),
            4,
        )

    @property
    def passed(self) -> bool:
        return (
            self.unexpected_failure_count == 0
            and self.silent_drift_count == 0
            and (self.fallback_success_count + self.structured_failure_count)
            == self.audited_case_count
        )


@dataclass(frozen=True)
class CapabilityTraceAuditResult:
    audited_case_count: int
    complete_trace_count: int
    incomplete_trace_count: int
    case_results: tuple[CapabilityAuditCaseResult, ...]

    @property
    def coverage(self) -> float:
        if self.audited_case_count == 0:
            return 1.0
        return round(self.complete_trace_count / float(self.audited_case_count), 4)

    @property
    def passed(self) -> bool:
        return self.incomplete_trace_count == 0


def evaluate_capability_failure_audit(
    scenarios: Iterable["CapabilityAdapterScenario"] | None = None,
    *,
    adapters: list[CapabilityAdapter] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> CapabilityFailureAuditResult:
    """Audit unavailable-provider scenarios for fallback or structured failure only."""

    scenario_list = tuple(scenarios or _default_scenarios())
    available_families = _available_provider_families(adapters)
    case_results: list[CapabilityAuditCaseResult] = []
    fallback_success_count = 0
    structured_failure_count = 0
    unexpected_failure_count = 0
    silent_drift_count = 0

    for scenario in scenario_list:
        if scenario.provider_family in available_families:
            continue
        case_result = _run_audit_case(
            scenario,
            adapters=adapters,
            clock=clock,
        )
        if case_result.outcome == "fallback_success":
            fallback_success_count += 1
        elif case_result.outcome == "structured_failure":
            structured_failure_count += 1
        elif case_result.outcome.startswith("silent_drift"):
            silent_drift_count += 1
        else:
            unexpected_failure_count += 1
        case_results.append(case_result)

    return CapabilityFailureAuditResult(
        audited_case_count=len(case_results),
        fallback_success_count=fallback_success_count,
        structured_failure_count=structured_failure_count,
        unexpected_failure_count=unexpected_failure_count,
        silent_drift_count=silent_drift_count,
        case_results=tuple(case_results),
    )


def evaluate_capability_trace_audit(
    scenarios: Iterable["CapabilityAdapterScenario"] | None = None,
    *,
    adapters: list[CapabilityAdapter] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> CapabilityTraceAuditResult:
    """Audit successful external-provider capability calls for complete trace fields."""

    scenario_list = tuple(scenarios or _default_scenarios())
    case_results: list[CapabilityAuditCaseResult] = []

    for scenario in scenario_list:
        if scenario.provider_family is CapabilityProviderFamily.DETERMINISTIC:
            continue
        case_result = _run_audit_case(
            scenario,
            adapters=adapters,
            clock=clock,
        )
        if case_result.outcome in {"fallback_success", "success"}:
            case_results.append(case_result)

    complete_trace_count = sum(result.trace_complete for result in case_results)
    return CapabilityTraceAuditResult(
        audited_case_count=len(case_results),
        complete_trace_count=complete_trace_count,
        incomplete_trace_count=len(case_results) - complete_trace_count,
        case_results=tuple(case_results),
    )


def assert_capability_failure_audit(result: CapabilityFailureAuditResult) -> None:
    if result.passed:
        return
    raise RuntimeError(
        "K-4 failed: "
        f"fallback_success={result.fallback_success_count}, "
        f"structured_failure={result.structured_failure_count}, "
        f"unexpected_failure={result.unexpected_failure_count}, "
        f"silent_drift={result.silent_drift_count}"
    )


def assert_capability_trace_audit(result: CapabilityTraceAuditResult) -> None:
    if result.passed:
        return
    raise RuntimeError(
        "K-6 failed: "
        f"complete_trace={result.complete_trace_count}/"
        f"{result.audited_case_count}"
    )


def _run_audit_case(
    scenario: "CapabilityAdapterScenario",
    *,
    adapters: list[CapabilityAdapter] | None,
    clock: Callable[[], datetime] | None,
) -> CapabilityAuditCaseResult:
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
        outcome = (
            "structured_failure"
            if scenario.request.fallback_policy is CapabilityFallbackPolicy.FAIL_CLOSED
            else "unexpected_failure"
        )
        return CapabilityAuditCaseResult(
            scenario_id=scenario.scenario_id,
            capability=scenario.capability,
            requested_provider_family=scenario.provider_family,
            fallback_policy=scenario.request.fallback_policy,
            outcome=outcome,
            fallback_used=False,
            trace_complete=False,
            trace_provider_family=None,
            error_message=str(exc),
        )

    if scenario.request.fallback_policy is CapabilityFallbackPolicy.FAIL_CLOSED:
        outcome = "silent_drift_fallback" if response.trace.fallback_used else "success"
    elif scenario.provider_family is CapabilityProviderFamily.DETERMINISTIC:
        outcome = "success"
    elif response.trace.fallback_used:
        outcome = "fallback_success"
    else:
        outcome = "success"

    return CapabilityAuditCaseResult(
        scenario_id=scenario.scenario_id,
        capability=scenario.capability,
        requested_provider_family=scenario.provider_family,
        fallback_policy=scenario.request.fallback_policy,
        outcome=outcome,
        fallback_used=response.trace.fallback_used,
        trace_complete=_trace_complete(response.trace),
        trace_provider_family=response.trace.provider_family,
        error_message=None,
    )


def _available_provider_families(
    adapters: list[CapabilityAdapter] | None,
) -> set[CapabilityProviderFamily]:
    return {
        CapabilityProviderFamily.DETERMINISTIC,
        *(adapter.descriptor.provider_family for adapter in adapters or []),
    }


def _trace_complete(trace: CapabilityInvocationTrace) -> bool:
    return bool(
        trace.provider_family
        and trace.model
        and trace.endpoint
        and trace.version
        and trace.started_at
        and trace.completed_at
        and trace.completed_at >= trace.started_at
        and trace.duration_ms >= 0
    )


def _default_scenarios() -> tuple["CapabilityAdapterScenario", ...]:
    from mind.fixtures.capability_adapter_bench import build_capability_adapter_bench_v1

    return build_capability_adapter_bench_v1()
