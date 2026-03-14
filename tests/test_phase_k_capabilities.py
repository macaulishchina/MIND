from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from mind.capabilities import (
    CAPABILITY_CATALOG,
    AnswerRequest,
    AnswerResponse,
    CapabilityAdapterDescriptor,
    CapabilityAdapterError,
    CapabilityFallbackPolicy,
    CapabilityInvocationTrace,
    CapabilityName,
    CapabilityProviderFamily,
    OfflineReconstructRequest,
    OfflineReconstructResponse,
    ReflectRequest,
    ReflectResponse,
    SummarizeRequest,
    SummarizeResponse,
    invoke_capability,
    request_model_for,
    response_model_for,
    validate_capability_response,
)
from mind.fixtures import build_capability_adapter_bench_v1


def _trace(
    *,
    provider_family: CapabilityProviderFamily = CapabilityProviderFamily.DETERMINISTIC,
) -> CapabilityInvocationTrace:
    started_at = datetime(2026, 3, 11, 12, 0, tzinfo=UTC)
    completed_at = datetime(2026, 3, 11, 12, 0, 1, tzinfo=UTC)
    return CapabilityInvocationTrace(
        provider_family=provider_family,
        model="deterministic",
        endpoint="local://deterministic",
        version="v1",
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=1000,
    )


def test_capability_catalog_is_frozen() -> None:
    assert CAPABILITY_CATALOG == (
        CapabilityName.SUMMARIZE,
        CapabilityName.REFLECT,
        CapabilityName.ANSWER,
        CapabilityName.OFFLINE_RECONSTRUCT,
    )


def test_trace_requires_fallback_reason_when_fallback_used() -> None:
    with pytest.raises(ValidationError, match="fallback_reason required"):
        CapabilityInvocationTrace(
            provider_family=CapabilityProviderFamily.OPENAI,
            model="gpt-4.1",
            endpoint="https://api.openai.example/v1/responses",
            version="2026-03-11",
            started_at=datetime(2026, 3, 11, 12, 0, tzinfo=UTC),
            completed_at=datetime(2026, 3, 11, 12, 0, 1, tzinfo=UTC),
            duration_ms=1000,
            fallback_used=True,
        )


def test_request_response_model_mapping_is_complete() -> None:
    assert request_model_for(CapabilityName.SUMMARIZE) is SummarizeRequest
    assert request_model_for(CapabilityName.REFLECT) is ReflectRequest
    assert request_model_for(CapabilityName.ANSWER) is AnswerRequest
    assert request_model_for(CapabilityName.OFFLINE_RECONSTRUCT) is OfflineReconstructRequest
    assert response_model_for(CapabilityName.SUMMARIZE) is SummarizeResponse
    assert response_model_for(CapabilityName.REFLECT) is ReflectResponse
    assert response_model_for(CapabilityName.ANSWER) is AnswerResponse
    assert response_model_for(CapabilityName.OFFLINE_RECONSTRUCT) is OfflineReconstructResponse


def test_offline_reconstruct_requires_episode_ids() -> None:
    with pytest.raises(ValidationError):
        OfflineReconstructRequest(
            request_id="offline-empty",
            objective="reconstruct",
            evidence_text="evidence",
            episode_ids=[],
        )


def test_validate_capability_response_rejects_wrong_response_type() -> None:
    request = SummarizeRequest(request_id="sum-1", source_text="source")
    wrong_response = AnswerResponse(
        answer_text="answer",
        support_ids=["obj-1"],
        trace=_trace(),
    )

    with pytest.raises(CapabilityAdapterError, match="unexpected response model"):
        validate_capability_response(request, wrong_response)


def test_invoke_capability_validates_support_and_response_shape() -> None:
    class _Adapter:
        descriptor = CapabilityAdapterDescriptor(
            adapter_name="deterministic-test",
            provider_family=CapabilityProviderFamily.DETERMINISTIC,
            model="deterministic",
            version="v1",
            api_style="deterministic",
            supported_capabilities=[CapabilityName.SUMMARIZE],
        )

        def invoke(self, request: SummarizeRequest) -> SummarizeResponse:
            return SummarizeResponse(
                summary_text=f"summary:{request.source_text}",
                source_refs=list(request.source_refs),
                trace=_trace(),
            )

    response = invoke_capability(
        _Adapter(),  # type: ignore[arg-type]
        SummarizeRequest(
            request_id="sum-invoke",
            source_text="source text",
            fallback_policy=CapabilityFallbackPolicy.ALLOW_DETERMINISTIC,
        ),
    )

    assert isinstance(response, SummarizeResponse)
    assert response.summary_text == "summary:source text"


def test_invoke_capability_rejects_unsupported_capability() -> None:
    class _Adapter:
        descriptor = CapabilityAdapterDescriptor(
            adapter_name="deterministic-test",
            provider_family=CapabilityProviderFamily.DETERMINISTIC,
            model="deterministic",
            version="v1",
            api_style="deterministic",
            supported_capabilities=[CapabilityName.SUMMARIZE],
        )

        def invoke(self, request: SummarizeRequest) -> SummarizeResponse:
            return SummarizeResponse(
                summary_text="summary",
                trace=_trace(),
            )

    with pytest.raises(CapabilityAdapterError, match="does not support answer"):
        invoke_capability(
            _Adapter(),  # type: ignore[arg-type]
            AnswerRequest(
                request_id="ans-unsupported",
                question="What happened?",
                context_text="context",
            ),
        )


def test_capability_adapter_bench_v1_is_complete_and_frozen() -> None:
    scenarios = build_capability_adapter_bench_v1()

    assert len(scenarios) == 48
    assert {scenario.capability for scenario in scenarios} == set(CAPABILITY_CATALOG)
    assert {scenario.provider_family for scenario in scenarios} == {
        CapabilityProviderFamily.DETERMINISTIC,
        CapabilityProviderFamily.OPENAI,
        CapabilityProviderFamily.CLAUDE,
        CapabilityProviderFamily.GEMINI,
    }

    per_pair_counts = {
        (capability, provider): sum(
            1
            for scenario in scenarios
            if scenario.capability is capability and scenario.provider_family is provider
        )
        for capability in CAPABILITY_CATALOG
        for provider in {
            CapabilityProviderFamily.DETERMINISTIC,
            CapabilityProviderFamily.OPENAI,
            CapabilityProviderFamily.CLAUDE,
            CapabilityProviderFamily.GEMINI,
        }
    }
    assert set(per_pair_counts.values()) == {3}

    for scenario in scenarios:
        assert isinstance(scenario.request, request_model_for(scenario.capability))
        assert scenario.expected_response_type is response_model_for(scenario.capability)
