from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from mind.capabilities import (
    CapabilityAdapterDescriptor,
    CapabilityAdapterError,
    CapabilityAuthConfig,
    CapabilityFallbackPolicy,
    CapabilityInvocationTrace,
    CapabilityName,
    CapabilityProviderConfig,
    CapabilityProviderFamily,
    CapabilityService,
    CapabilityServiceError,
    GeminiCapabilityAdapter,
    ReflectRequest,
    ReflectResponse,
    SummarizeRequest,
    SummarizeResponse,
)


def _fixed_clock() -> datetime:
    return datetime(2026, 3, 11, 20, 0, tzinfo=UTC)


def _gemini_config() -> CapabilityProviderConfig:
    return CapabilityProviderConfig(
        provider="gemini",
        provider_family=CapabilityProviderFamily.GEMINI,
        model="gemini-2.0-flash",
        endpoint="https://generativelanguage.googleapis.com/v1beta/models",
        api_version="v1beta",
        timeout_ms=20_000,
        retry_policy="default",
        auth=CapabilityAuthConfig(
            mode="api_key",
            secret_env="GOOGLE_API_KEY",
            secret_value="gemini-secret",
            parameter_name="key",
        ),
    )


def test_gemini_adapter_posts_generate_content_request() -> None:
    captured: dict[str, Any] = {}

    def _transport(
        endpoint: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout_seconds: float | None,
    ) -> dict[str, Any]:
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout_seconds"] = timeout_seconds
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps({"summary_text": "gemini summary"}),
                            }
                        ]
                    }
                }
            ]
        }

    adapter = GeminiCapabilityAdapter(
        _gemini_config(),
        clock=_fixed_clock,
        transport=_transport,
    )
    response = adapter.invoke(
        SummarizeRequest(
            request_id="sum-gemini",
            source_text="source text for gemini summary",
            source_refs=["obj-3"],
            instruction="Summarize for operator handoff.",
            max_output_tokens=80,
        )
    )

    assert response.summary_text == "gemini summary"
    assert response.source_refs == ["obj-3"]
    assert response.trace.provider_family is CapabilityProviderFamily.GEMINI
    assert captured["endpoint"] == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.0-flash:generateContent"
    )
    assert captured["headers"]["x-goog-api-key"] == "gemini-secret"
    assert captured["payload"]["generationConfig"]["responseMimeType"] == "application/json"
    assert captured["payload"]["generationConfig"]["maxOutputTokens"] == 80
    assert captured["payload"]["contents"][0]["parts"][0]["text"].startswith(
        "You are the MIND summarize capability."
    )


def test_gemini_adapter_parses_reflect_claims() -> None:
    adapter = GeminiCapabilityAdapter(
        _gemini_config(),
        clock=_fixed_clock,
        transport=lambda *_args, **_kwargs: {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "reflection_text": "Episode failed; reflection focus: stale memory",
                                        "claims": ["stale-memory", "refresh-cache"],
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        },
    )

    response = adapter.invoke(
        ReflectRequest(
            request_id="reflect-gemini",
            focus="failure postmortem",
            evidence_text="stale memory caused repeated mismatch",
            episode_id="episode-004",
            evidence_refs=["episode-004", "episode-004-raw-04"],
            outcome_hint="failure",
        )
    )

    assert isinstance(response, ReflectResponse)
    assert response.reflection_text.startswith("Episode failed")
    assert response.claims == ["stale-memory", "refresh-cache"]
    assert response.evidence_refs == ["episode-004", "episode-004-raw-04"]


def test_gemini_adapter_rejects_invalid_json_payload() -> None:
    adapter = GeminiCapabilityAdapter(
        _gemini_config(),
        clock=_fixed_clock,
        transport=lambda *_args, **_kwargs: {
            "candidates": [{"content": {"parts": [{"text": "not-json"}]}}],
        },
    )

    with pytest.raises(CapabilityAdapterError, match="valid JSON output"):
        adapter.invoke(SummarizeRequest(request_id="sum-invalid", source_text="source"))


def test_capability_service_builds_gemini_adapter_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, SummarizeRequest] = {}

    class _FakeGeminiAdapter:
        def __init__(
            self,
            config: CapabilityProviderConfig,
            *,
            clock: Any = None,
            transport: Any = None,
        ) -> None:
            self.descriptor = CapabilityAdapterDescriptor(
                adapter_name="fake-gemini-adapter",
                provider_family=CapabilityProviderFamily.GEMINI,
                model=config.model,
                version=config.api_version or "v1beta",
                api_style="generateContent",
                supported_capabilities=list(CapabilityName),
            )

        def invoke(self, request: SummarizeRequest) -> SummarizeResponse:
            captured["request"] = request
            return SummarizeResponse(
                summary_text="gemini adapter response",
                source_refs=list(request.source_refs),
                trace=_gemini_trace(),
            )

    monkeypatch.setattr("mind.capabilities.service.GeminiCapabilityAdapter", _FakeGeminiAdapter)
    service = CapabilityService(provider_config=_gemini_config(), clock=_fixed_clock)

    response = service.summarize(
        SummarizeRequest(
            request_id="sum-service-gemini",
            source_text="provider source text",
            source_refs=["obj-9"],
        )
    )

    assert captured["request"].source_refs == ["obj-9"]
    assert response.summary_text == "gemini adapter response"
    assert response.trace.provider_family is CapabilityProviderFamily.GEMINI


def test_capability_service_falls_back_when_gemini_adapter_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingGeminiAdapter:
        def __init__(self, config: CapabilityProviderConfig, *, clock: Any = None) -> None:
            self.descriptor = CapabilityAdapterDescriptor(
                adapter_name="failing-gemini-adapter",
                provider_family=CapabilityProviderFamily.GEMINI,
                model=config.model,
                version=config.api_version or "v1beta",
                api_style="generateContent",
                supported_capabilities=[CapabilityName.SUMMARIZE],
            )

        def invoke(self, request: SummarizeRequest) -> SummarizeResponse:
            raise CapabilityAdapterError("gemini transport failed")

    monkeypatch.setattr("mind.capabilities.service.GeminiCapabilityAdapter", _FailingGeminiAdapter)
    service = CapabilityService(provider_config=_gemini_config(), clock=_fixed_clock)

    response = service.summarize(
        SummarizeRequest(request_id="sum-gemini-fallback", source_text="fallback source text")
    )

    assert response.trace.provider_family is CapabilityProviderFamily.DETERMINISTIC
    assert response.trace.fallback_used is True
    assert "gemini transport failed" in str(response.trace.fallback_reason)


def test_capability_service_fail_closed_when_gemini_adapter_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingGeminiAdapter:
        def __init__(self, config: CapabilityProviderConfig, *, clock: Any = None) -> None:
            self.descriptor = CapabilityAdapterDescriptor(
                adapter_name="failing-gemini-adapter",
                provider_family=CapabilityProviderFamily.GEMINI,
                model=config.model,
                version=config.api_version or "v1beta",
                api_style="generateContent",
                supported_capabilities=[CapabilityName.SUMMARIZE],
            )

        def invoke(self, request: SummarizeRequest) -> SummarizeResponse:
            raise CapabilityAdapterError("gemini transport failed")

    monkeypatch.setattr("mind.capabilities.service.GeminiCapabilityAdapter", _FailingGeminiAdapter)
    service = CapabilityService(provider_config=_gemini_config(), clock=_fixed_clock)

    with pytest.raises(CapabilityServiceError, match="primary capability adapter failed for gemini"):
        service.summarize(
            SummarizeRequest(
                request_id="sum-gemini-fail-closed",
                source_text="provider source text",
                fallback_policy=CapabilityFallbackPolicy.FAIL_CLOSED,
            )
        )


def _gemini_trace() -> CapabilityInvocationTrace:
    return CapabilityInvocationTrace(
        provider_family=CapabilityProviderFamily.GEMINI,
        model="gemini-2.0-flash",
        endpoint="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        version="v1beta",
        started_at=_fixed_clock(),
        completed_at=_fixed_clock(),
        duration_ms=0,
    )
