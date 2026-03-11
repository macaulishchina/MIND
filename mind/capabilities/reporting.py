"""Reporting helpers for Phase K capability compatibility audits."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .audit import (
    CapabilityFailureAuditResult,
    CapabilityTraceAuditResult,
    evaluate_capability_failure_audit,
    evaluate_capability_trace_audit,
)
from .benchmark import CapabilityBenchmarkResult, evaluate_capability_adapter_bench
from .contracts import CapabilityProviderFamily

_SCHEMA_VERSION = "capability_provider_compatibility_report_v1"


@dataclass(frozen=True)
class CapabilityProviderCompatibilitySummary:
    provider_family: CapabilityProviderFamily
    benchmark_case_count: int
    benchmark_passed_case_count: int
    benchmark_failed_case_count: int
    benchmark_pass_rate: float
    failure_audit_case_count: int
    fallback_success_count: int
    structured_failure_count: int
    silent_drift_count: int
    trace_audited_case_count: int
    trace_complete_count: int
    trace_coverage: float


@dataclass(frozen=True)
class CapabilityProviderCompatibilityReport:
    schema_version: str
    generated_at: str
    benchmark_case_count: int
    benchmark_pass_rate: float
    failure_audit_pass_rate: float
    trace_audit_coverage: float
    providers: tuple[CapabilityProviderCompatibilitySummary, ...]


def evaluate_capability_provider_compatibility_report(
    *,
    adapters: list[Any] | None = None,
    clock: Any = None,
    generated_at: datetime | None = None,
) -> CapabilityProviderCompatibilityReport:
    benchmark_result = evaluate_capability_adapter_bench(adapters=adapters, clock=clock)
    failure_audit = evaluate_capability_failure_audit(adapters=adapters, clock=clock)
    trace_audit = evaluate_capability_trace_audit(adapters=adapters, clock=clock)
    return build_capability_provider_compatibility_report(
        benchmark_result=benchmark_result,
        failure_audit=failure_audit,
        trace_audit=trace_audit,
        generated_at=generated_at,
    )


def build_capability_provider_compatibility_report(
    *,
    benchmark_result: CapabilityBenchmarkResult,
    failure_audit: CapabilityFailureAuditResult,
    trace_audit: CapabilityTraceAuditResult,
    generated_at: datetime | None = None,
) -> CapabilityProviderCompatibilityReport:
    providers = tuple(
        _provider_summary(provider, benchmark_result, failure_audit, trace_audit)
        for provider in CapabilityProviderFamily
    )
    return CapabilityProviderCompatibilityReport(
        schema_version=_SCHEMA_VERSION,
        generated_at=(generated_at or datetime.now(UTC)).isoformat(),
        benchmark_case_count=benchmark_result.case_count,
        benchmark_pass_rate=benchmark_result.pass_rate,
        failure_audit_pass_rate=failure_audit.pass_rate,
        trace_audit_coverage=trace_audit.coverage,
        providers=providers,
    )


def write_capability_provider_compatibility_report_json(
    path: str | Path,
    report: CapabilityProviderCompatibilityReport,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_report_to_dict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def read_capability_provider_compatibility_report_json(
    path: str | Path,
) -> CapabilityProviderCompatibilityReport:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError(
            "unexpected capability compatibility report schema_version "
            f"({payload.get('schema_version')!r})"
        )
    return _report_from_dict(payload)


def _provider_summary(
    provider: CapabilityProviderFamily,
    benchmark_result: CapabilityBenchmarkResult,
    failure_audit: CapabilityFailureAuditResult,
    trace_audit: CapabilityTraceAuditResult,
) -> CapabilityProviderCompatibilitySummary:
    benchmark_cases = [
        case for case in benchmark_result.case_results if case.provider_family is provider
    ]
    failure_cases = [
        case for case in failure_audit.case_results if case.requested_provider_family is provider
    ]
    trace_cases = [
        case for case in trace_audit.case_results if case.requested_provider_family is provider
    ]
    benchmark_case_count = len(benchmark_cases)
    benchmark_passed_case_count = sum(case.passed for case in benchmark_cases)
    trace_audited_case_count = len(trace_cases)
    trace_complete_count = sum(case.trace_complete for case in trace_cases)
    return CapabilityProviderCompatibilitySummary(
        provider_family=provider,
        benchmark_case_count=benchmark_case_count,
        benchmark_passed_case_count=benchmark_passed_case_count,
        benchmark_failed_case_count=benchmark_case_count - benchmark_passed_case_count,
        benchmark_pass_rate=_safe_ratio(benchmark_passed_case_count, benchmark_case_count),
        failure_audit_case_count=len(failure_cases),
        fallback_success_count=sum(case.outcome == "fallback_success" for case in failure_cases),
        structured_failure_count=sum(
            case.outcome == "structured_failure" for case in failure_cases
        ),
        silent_drift_count=sum(case.outcome.startswith("silent_drift") for case in failure_cases),
        trace_audited_case_count=trace_audited_case_count,
        trace_complete_count=trace_complete_count,
        trace_coverage=_safe_ratio(trace_complete_count, trace_audited_case_count),
    )


def _report_to_dict(report: CapabilityProviderCompatibilityReport) -> dict[str, object]:
    return {
        "schema_version": report.schema_version,
        "generated_at": report.generated_at,
        "benchmark_case_count": report.benchmark_case_count,
        "benchmark_pass_rate": report.benchmark_pass_rate,
        "failure_audit_pass_rate": report.failure_audit_pass_rate,
        "trace_audit_coverage": report.trace_audit_coverage,
        "providers": [_provider_to_dict(provider) for provider in report.providers],
    }


def _provider_to_dict(
    provider: CapabilityProviderCompatibilitySummary,
) -> dict[str, object]:
    return {
        "provider_family": provider.provider_family.value,
        "benchmark_case_count": provider.benchmark_case_count,
        "benchmark_passed_case_count": provider.benchmark_passed_case_count,
        "benchmark_failed_case_count": provider.benchmark_failed_case_count,
        "benchmark_pass_rate": provider.benchmark_pass_rate,
        "failure_audit_case_count": provider.failure_audit_case_count,
        "fallback_success_count": provider.fallback_success_count,
        "structured_failure_count": provider.structured_failure_count,
        "silent_drift_count": provider.silent_drift_count,
        "trace_audited_case_count": provider.trace_audited_case_count,
        "trace_complete_count": provider.trace_complete_count,
        "trace_coverage": provider.trace_coverage,
    }


def _report_from_dict(payload: dict[str, Any]) -> CapabilityProviderCompatibilityReport:
    return CapabilityProviderCompatibilityReport(
        schema_version=str(payload["schema_version"]),
        generated_at=str(payload["generated_at"]),
        benchmark_case_count=int(payload["benchmark_case_count"]),
        benchmark_pass_rate=float(payload["benchmark_pass_rate"]),
        failure_audit_pass_rate=float(payload["failure_audit_pass_rate"]),
        trace_audit_coverage=float(payload["trace_audit_coverage"]),
        providers=tuple(_provider_from_dict(provider) for provider in payload["providers"]),
    )


def _provider_from_dict(payload: dict[str, Any]) -> CapabilityProviderCompatibilitySummary:
    return CapabilityProviderCompatibilitySummary(
        provider_family=CapabilityProviderFamily(str(payload["provider_family"])),
        benchmark_case_count=int(payload["benchmark_case_count"]),
        benchmark_passed_case_count=int(payload["benchmark_passed_case_count"]),
        benchmark_failed_case_count=int(payload["benchmark_failed_case_count"]),
        benchmark_pass_rate=float(payload["benchmark_pass_rate"]),
        failure_audit_case_count=int(payload["failure_audit_case_count"]),
        fallback_success_count=int(payload["fallback_success_count"]),
        structured_failure_count=int(payload["structured_failure_count"]),
        silent_drift_count=int(payload["silent_drift_count"]),
        trace_audited_case_count=int(payload["trace_audited_case_count"]),
        trace_complete_count=int(payload["trace_complete_count"]),
        trace_coverage=float(payload["trace_coverage"]),
    )


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / float(denominator), 4)
