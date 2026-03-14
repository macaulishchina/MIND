from __future__ import annotations

from datetime import UTC, datetime

import pytest

from mind.capabilities import (
    CapabilityAdapterDescriptor,
    CapabilityInvocationTrace,
    CapabilityName,
    CapabilityProviderFamily,
    CapabilityRequest,
    CapabilityResponse,
    DeterministicCapabilityAdapter,
    assert_capability_adapter_bench,
    evaluate_capability_adapter_bench,
)


def _fixed_clock() -> datetime:
    return datetime(2026, 3, 11, 16, 0, tzinfo=UTC)


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


def test_capability_adapter_bench_reports_current_baseline() -> None:
    result = evaluate_capability_adapter_bench(clock=_fixed_clock)

    assert result.case_count == 48
    assert result.passed_case_count == 36
    assert result.failed_case_count == 12
    assert result.pass_rate == 0.75
    assert all("fail_closed" in case.scenario_id for case in result.case_results if not case.passed)


def test_capability_adapter_bench_improves_when_provider_adapter_is_registered() -> None:
    result = evaluate_capability_adapter_bench(
        adapters=[_OpenAICapabilityAdapter()],
        clock=_fixed_clock,
    )

    assert result.case_count == 48
    assert result.passed_case_count == 40
    assert result.failed_case_count == 8
    assert result.pass_rate == 0.8333
    assert all(
        case.provider_family is not CapabilityProviderFamily.OPENAI
        for case in result.case_results
        if not case.passed
    )


def test_assert_capability_adapter_bench_enforces_threshold() -> None:
    result = evaluate_capability_adapter_bench(clock=_fixed_clock)

    with pytest.raises(RuntimeError, match="K-7 failed"):
        assert_capability_adapter_bench(result)

    assert_capability_adapter_bench(result, min_pass_rate=0.70)
