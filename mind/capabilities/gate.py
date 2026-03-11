"""Phase K formal gate evaluation helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .adapter import CapabilityAdapter
from .audit import (
    CapabilityFailureAuditResult,
    CapabilityTraceAuditResult,
    evaluate_capability_failure_audit,
    evaluate_capability_trace_audit,
)
from .benchmark import CapabilityBenchmarkResult, evaluate_capability_adapter_bench
from .contracts import (
    CAPABILITY_CATALOG,
    CapabilityProviderFamily,
    request_model_for,
    response_model_for,
)
from .reporting import (
    CapabilityProviderCompatibilityReport,
    evaluate_capability_provider_compatibility_report,
)

_SCHEMA_VERSION = "capability_gate_report_v1"
_FIXED_TIMESTAMP = datetime(2026, 3, 11, 21, 0, tzinfo=UTC)
_EXTERNAL_PROVIDERS = (
    CapabilityProviderFamily.OPENAI,
    CapabilityProviderFamily.CLAUDE,
    CapabilityProviderFamily.GEMINI,
)


@dataclass(frozen=True)
class CapabilityContractAuditResult:
    capability_count: int
    request_contract_count: int
    response_contract_count: int
    missing_request_contracts: tuple[str, ...]
    missing_response_contracts: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return (
            self.capability_count == 4
            and self.request_contract_count == 4
            and self.response_contract_count == 4
            and not self.missing_request_contracts
            and not self.missing_response_contracts
        )


@dataclass(frozen=True)
class CapabilityGateResult:
    contract_audit: CapabilityContractAuditResult
    benchmark_result: CapabilityBenchmarkResult
    failure_audit: CapabilityFailureAuditResult
    trace_audit: CapabilityTraceAuditResult
    compatibility_report: CapabilityProviderCompatibilityReport

    @property
    def k1_pass(self) -> bool:
        return self.contract_audit.passed

    @property
    def k2_pass(self) -> bool:
        provider_map = {
            summary.provider_family: summary for summary in self.compatibility_report.providers
        }
        return all(
            provider_map[provider].benchmark_pass_rate == 1.0 for provider in _EXTERNAL_PROVIDERS
        )

    @property
    def k3_pass(self) -> bool:
        provider_map = {
            summary.provider_family: summary for summary in self.compatibility_report.providers
        }
        return all(
            provider_map[provider].benchmark_failed_case_count == 0 for provider in _EXTERNAL_PROVIDERS
        )

    @property
    def k4_pass(self) -> bool:
        return self.failure_audit.passed

    @property
    def k5_pass(self) -> bool:
        provider_map = {
            summary.provider_family: summary for summary in self.compatibility_report.providers
        }
        return provider_map[CapabilityProviderFamily.DETERMINISTIC].benchmark_pass_rate == 1.0

    @property
    def k6_pass(self) -> bool:
        return self.trace_audit.passed

    @property
    def k7_pass(self) -> bool:
        return self.benchmark_result.pass_rate >= 0.95

    @property
    def capability_gate_pass(self) -> bool:
        return (
            self.k1_pass
            and self.k2_pass
            and self.k3_pass
            and self.k4_pass
            and self.k5_pass
            and self.k6_pass
            and self.k7_pass
        )


def evaluate_capability_contract_audit() -> CapabilityContractAuditResult:
    missing_request_contracts: list[str] = []
    missing_response_contracts: list[str] = []
    request_contract_count = 0
    response_contract_count = 0
    for capability in CAPABILITY_CATALOG:
        try:
            request_model_for(capability)
            request_contract_count += 1
        except Exception:
            missing_request_contracts.append(capability.value)
        try:
            response_model_for(capability)
            response_contract_count += 1
        except Exception:
            missing_response_contracts.append(capability.value)
    return CapabilityContractAuditResult(
        capability_count=len(CAPABILITY_CATALOG),
        request_contract_count=request_contract_count,
        response_contract_count=response_contract_count,
        missing_request_contracts=tuple(missing_request_contracts),
        missing_response_contracts=tuple(missing_response_contracts),
    )


def evaluate_capability_gate(
    *,
    adapters: list[CapabilityAdapter] | None = None,
) -> CapabilityGateResult:
    benchmark_result = evaluate_capability_adapter_bench(
        adapters=adapters,
        clock=lambda: _FIXED_TIMESTAMP,
    )
    failure_audit = evaluate_capability_failure_audit(
        adapters=adapters,
        clock=lambda: _FIXED_TIMESTAMP,
    )
    trace_audit = evaluate_capability_trace_audit(
        adapters=adapters,
        clock=lambda: _FIXED_TIMESTAMP,
    )
    compatibility_report = evaluate_capability_provider_compatibility_report(
        adapters=adapters,
        clock=lambda: _FIXED_TIMESTAMP,
        generated_at=_FIXED_TIMESTAMP,
    )
    return CapabilityGateResult(
        contract_audit=evaluate_capability_contract_audit(),
        benchmark_result=benchmark_result,
        failure_audit=failure_audit,
        trace_audit=trace_audit,
        compatibility_report=compatibility_report,
    )


def assert_capability_gate(result: CapabilityGateResult) -> None:
    if not result.k1_pass:
        raise RuntimeError("K-1 failed: capability contracts are incomplete")
    if not result.k2_pass:
        raise RuntimeError("K-2 failed: provider compatibility coverage is incomplete")
    if not result.k3_pass:
        raise RuntimeError("K-3 failed: provider switching is not transparent")
    if not result.k4_pass:
        raise RuntimeError("K-4 failed: fallback / failure audit did not converge")
    if not result.k5_pass:
        raise RuntimeError("K-5 failed: deterministic baseline regressed")
    if not result.k6_pass:
        raise RuntimeError("K-6 failed: trace coverage is incomplete")
    if not result.k7_pass:
        raise RuntimeError(
            f"K-7 failed: adapter bench pass_rate={result.benchmark_result.pass_rate:.4f}"
        )


def write_capability_gate_report_json(path: str | Path, result: CapabilityGateResult) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_report_payload(result), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def _report_payload(result: CapabilityGateResult) -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": _FIXED_TIMESTAMP.isoformat(),
        "capability_gate_pass": result.capability_gate_pass,
        "k1_pass": result.k1_pass,
        "k2_pass": result.k2_pass,
        "k3_pass": result.k3_pass,
        "k4_pass": result.k4_pass,
        "k5_pass": result.k5_pass,
        "k6_pass": result.k6_pass,
        "k7_pass": result.k7_pass,
        "contract_audit": {
            "capability_count": result.contract_audit.capability_count,
            "request_contract_count": result.contract_audit.request_contract_count,
            "response_contract_count": result.contract_audit.response_contract_count,
            "missing_request_contracts": list(result.contract_audit.missing_request_contracts),
            "missing_response_contracts": list(result.contract_audit.missing_response_contracts),
        },
        "benchmark_result": {
            "case_count": result.benchmark_result.case_count,
            "passed_case_count": result.benchmark_result.passed_case_count,
            "failed_case_count": result.benchmark_result.failed_case_count,
            "pass_rate": result.benchmark_result.pass_rate,
        },
        "failure_audit": {
            "audited_case_count": result.failure_audit.audited_case_count,
            "fallback_success_count": result.failure_audit.fallback_success_count,
            "structured_failure_count": result.failure_audit.structured_failure_count,
            "unexpected_failure_count": result.failure_audit.unexpected_failure_count,
            "silent_drift_count": result.failure_audit.silent_drift_count,
            "pass_rate": result.failure_audit.pass_rate,
        },
        "trace_audit": {
            "audited_case_count": result.trace_audit.audited_case_count,
            "complete_trace_count": result.trace_audit.complete_trace_count,
            "incomplete_trace_count": result.trace_audit.incomplete_trace_count,
            "coverage": result.trace_audit.coverage,
        },
        "compatibility_report": {
            "schema_version": result.compatibility_report.schema_version,
            "benchmark_case_count": result.compatibility_report.benchmark_case_count,
            "benchmark_pass_rate": result.compatibility_report.benchmark_pass_rate,
            "failure_audit_pass_rate": result.compatibility_report.failure_audit_pass_rate,
            "trace_audit_coverage": result.compatibility_report.trace_audit_coverage,
            "providers": [
                {
                    "provider_family": summary.provider_family.value,
                    "benchmark_pass_rate": summary.benchmark_pass_rate,
                    "benchmark_failed_case_count": summary.benchmark_failed_case_count,
                    "failure_audit_case_count": summary.failure_audit_case_count,
                    "trace_coverage": summary.trace_coverage,
                }
                for summary in result.compatibility_report.providers
            ],
        },
    }
