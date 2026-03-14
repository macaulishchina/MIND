from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mind.capabilities import (
    CapabilityAdapterDescriptor,
    CapabilityInvocationTrace,
    CapabilityName,
    CapabilityProviderFamily,
    CapabilityRequest,
    CapabilityResponse,
    DeterministicCapabilityAdapter,
    build_capability_provider_compatibility_report,
    evaluate_capability_adapter_bench,
    evaluate_capability_failure_audit,
    evaluate_capability_provider_compatibility_report,
    evaluate_capability_trace_audit,
    read_capability_provider_compatibility_report_json,
    write_capability_provider_compatibility_report_json,
)


def _fixed_clock() -> datetime:
    return datetime(2026, 3, 11, 18, 0, tzinfo=UTC)


class _OpenAICapabilityAdapter:
    def __init__(self) -> None:
        self._baseline = DeterministicCapabilityAdapter(clock=_fixed_clock)
        self.descriptor = CapabilityAdapterDescriptor(
            adapter_name="openai-test-adapter",
            provider_family=CapabilityProviderFamily.OPENAI,
            model="gpt-4.1-mini",
            version="v1",
            api_style="responses",
            supported_capabilities=list(CapabilityName),
        )

    def invoke(self, request: CapabilityRequest) -> CapabilityResponse:
        response = self._baseline.invoke(request)
        return response.model_copy(
            update={
                "trace": CapabilityInvocationTrace(
                    provider_family=CapabilityProviderFamily.OPENAI,
                    model="gpt-4.1-mini",
                    endpoint="https://api.openai.com/v1/responses",
                    version="v1",
                    started_at=_fixed_clock(),
                    completed_at=_fixed_clock(),
                    duration_ms=0,
                )
            }
        )


def test_provider_compatibility_report_summarizes_current_baseline() -> None:
    report = evaluate_capability_provider_compatibility_report(
        clock=_fixed_clock,
        generated_at=datetime(2026, 3, 11, 18, 30, tzinfo=UTC),
    )

    assert report.schema_version == "capability_provider_compatibility_report_v1"
    assert report.benchmark_case_count == 48
    assert report.benchmark_pass_rate == 0.75
    assert report.failure_audit_pass_rate == 1.0
    assert report.trace_audit_coverage == 1.0

    providers = {summary.provider_family: summary for summary in report.providers}
    assert providers[CapabilityProviderFamily.DETERMINISTIC].benchmark_pass_rate == 1.0
    assert providers[CapabilityProviderFamily.OPENAI].benchmark_pass_rate == 0.6667
    assert providers[CapabilityProviderFamily.OPENAI].fallback_success_count == 8
    assert providers[CapabilityProviderFamily.OPENAI].structured_failure_count == 4
    assert providers[CapabilityProviderFamily.OPENAI].trace_coverage == 1.0
    assert providers[CapabilityProviderFamily.CLAUDE].benchmark_pass_rate == 0.6667
    assert providers[CapabilityProviderFamily.GEMINI].benchmark_pass_rate == 0.6667


def test_provider_compatibility_report_round_trips(tmp_path: Path) -> None:
    benchmark_result = evaluate_capability_adapter_bench(clock=_fixed_clock)
    failure_audit = evaluate_capability_failure_audit(clock=_fixed_clock)
    trace_audit = evaluate_capability_trace_audit(clock=_fixed_clock)
    report = build_capability_provider_compatibility_report(
        benchmark_result=benchmark_result,
        failure_audit=failure_audit,
        trace_audit=trace_audit,
        generated_at=datetime(2026, 3, 11, 18, 45, tzinfo=UTC),
    )

    output_path = write_capability_provider_compatibility_report_json(
        tmp_path / "phase_k_provider_compatibility.json",
        report,
    )
    reloaded = read_capability_provider_compatibility_report_json(output_path)

    assert reloaded == report


def test_provider_compatibility_report_reflects_registered_openai_adapter() -> None:
    report = evaluate_capability_provider_compatibility_report(
        adapters=[_OpenAICapabilityAdapter()],
        clock=_fixed_clock,
    )

    providers = {summary.provider_family: summary for summary in report.providers}
    assert providers[CapabilityProviderFamily.OPENAI].benchmark_pass_rate == 1.0
    assert providers[CapabilityProviderFamily.OPENAI].failure_audit_case_count == 0
    assert providers[CapabilityProviderFamily.OPENAI].trace_audited_case_count == 12
