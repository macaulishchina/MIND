from __future__ import annotations

from datetime import UTC, datetime

from mind.capabilities import (
    CapabilityAdapterDescriptor,
    CapabilityInvocationTrace,
    CapabilityName,
    CapabilityProviderFamily,
    CapabilityRequest,
    CapabilityResponse,
    DeterministicCapabilityAdapter,
    assert_capability_failure_audit,
    assert_capability_trace_audit,
    evaluate_capability_failure_audit,
    evaluate_capability_trace_audit,
)


def _fixed_clock() -> datetime:
    return datetime(2026, 3, 11, 15, 0, tzinfo=UTC)


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


def test_failure_audit_covers_unavailable_provider_scenarios() -> None:
    result = evaluate_capability_failure_audit(clock=_fixed_clock)

    assert result.audited_case_count == 36
    assert result.fallback_success_count == 24
    assert result.structured_failure_count == 12
    assert result.unexpected_failure_count == 0
    assert result.silent_drift_count == 0
    assert result.pass_rate == 1.0
    assert_capability_failure_audit(result)


def test_failure_audit_skips_provider_families_with_registered_adapter() -> None:
    result = evaluate_capability_failure_audit(
        adapters=[_OpenAICapabilityAdapter()],  # type: ignore[list-item]
        clock=_fixed_clock,
    )

    assert result.audited_case_count == 24
    assert all(
        case.requested_provider_family is not CapabilityProviderFamily.OPENAI
        for case in result.case_results
    )


def test_trace_audit_reports_complete_traces_for_successful_external_calls() -> None:
    result = evaluate_capability_trace_audit(clock=_fixed_clock)

    assert result.audited_case_count == 24
    assert result.complete_trace_count == 24
    assert result.incomplete_trace_count == 0
    assert all(case.trace_complete for case in result.case_results)
    assert_capability_trace_audit(result)
