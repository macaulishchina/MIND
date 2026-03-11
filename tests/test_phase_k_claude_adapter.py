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
    ClaudeCapabilityAdapter,
    ReflectRequest,
    ReflectResponse,
    SummarizeRequest,
    SummarizeResponse,
)


def _fixed_clock() -> datetime:
    return datetime(2026, 3, 11, 19, 0, tzinfo=UTC)


def _claude_config() -> CapabilityProviderConfig:
    return CapabilityProviderConfig(
        provider="claude",
        provider_family=CapabilityProviderFamily.CLAUDE,
        model="claude-3-7-sonnet",
        endpoint="https://api.anthropic.com/v1/messages",
        api_version="2023-06-01",
        timeout_ms=20_000,
        retry_policy="default",
        auth=CapabilityAuthConfig(
            mode="api_key",
            secret_env="ANTHROPIC_API_KEY",
            secret_value="claude-secret",
            parameter_name="x-api-key",
        ),
    )


def test_claude_adapter_posts_messages_request() -> None:
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
            "id": "msg_123",
            "model": "claude-3-7-sonnet",
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({"summary_text": "claude summary"}),
                }
            ],
        }

    adapter = ClaudeCapabilityAdapter(
        _claude_config(),
        clock=_fixed_clock,
        transport=_transport,
    )
    response = adapter.invoke(
        SummarizeRequest(
            request_id="sum-claude",
            source_text="source text for claude summary",
            source_refs=["obj-2"],
            instruction="Summarize for on-call handoff.",
            max_output_tokens=96,
        )
    )

    assert response.summary_text == "claude summary"
    assert response.source_refs == ["obj-2"]
    assert response.trace.provider_family is CapabilityProviderFamily.CLAUDE
    assert captured["endpoint"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "claude-secret"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["payload"]["model"] == "claude-3-7-sonnet"
    assert captured["payload"]["max_tokens"] == 96
    assert captured["payload"]["messages"][0]["role"] == "user"
    assert "Summarize for on-call handoff." in captured["payload"]["messages"][0]["content"]


def test_claude_adapter_parses_reflect_claims() -> None:
    adapter = ClaudeCapabilityAdapter(
        _claude_config(),
        clock=_fixed_clock,
        transport=lambda *_args, **_kwargs: {
            "model": "claude-3-7-sonnet",
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "reflection_text": "Episode failed; reflection focus: stale memory",
                            "claims": ["stale-memory", "retry-loop"],
                        }
                    ),
                }
            ],
        },
    )

    response = adapter.invoke(
        ReflectRequest(
            request_id="reflect-claude",
            focus="failure postmortem",
            evidence_text="stale memory caused repeated mismatch",
            episode_id="episode-004",
            evidence_refs=["episode-004", "episode-004-raw-04"],
            outcome_hint="failure",
        )
    )

    assert isinstance(response, ReflectResponse)
    assert response.reflection_text.startswith("Episode failed")
    assert response.claims == ["stale-memory", "retry-loop"]
    assert response.evidence_refs == ["episode-004", "episode-004-raw-04"]


def test_claude_adapter_rejects_invalid_json_payload() -> None:
    adapter = ClaudeCapabilityAdapter(
        _claude_config(),
        clock=_fixed_clock,
        transport=lambda *_args, **_kwargs: {
            "model": "claude-3-7-sonnet",
            "content": [{"type": "text", "text": "not-json"}],
        },
    )

    with pytest.raises(CapabilityAdapterError, match="valid JSON output"):
        adapter.invoke(SummarizeRequest(request_id="sum-invalid", source_text="source"))


def test_capability_service_builds_claude_adapter_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, SummarizeRequest] = {}

    class _FakeClaudeAdapter:
        def __init__(
            self,
            config: CapabilityProviderConfig,
            *,
            clock: Any = None,
            transport: Any = None,
        ) -> None:
            self.descriptor = CapabilityAdapterDescriptor(
                adapter_name="fake-claude-adapter",
                provider_family=CapabilityProviderFamily.CLAUDE,
                model=config.model,
                version=config.api_version or "2023-06-01",
                api_style="messages",
                supported_capabilities=list(CapabilityName),
            )

        def invoke(self, request: SummarizeRequest) -> SummarizeResponse:
            captured["request"] = request
            return SummarizeResponse(
                summary_text="claude adapter response",
                source_refs=list(request.source_refs),
                trace=_claude_trace(),
            )

    monkeypatch.setattr("mind.capabilities.service.ClaudeCapabilityAdapter", _FakeClaudeAdapter)
    service = CapabilityService(provider_config=_claude_config(), clock=_fixed_clock)

    response = service.summarize(
        SummarizeRequest(
            request_id="sum-service-claude",
            source_text="provider source text",
            source_refs=["obj-8"],
        )
    )

    assert captured["request"].source_refs == ["obj-8"]
    assert response.summary_text == "claude adapter response"
    assert response.trace.provider_family is CapabilityProviderFamily.CLAUDE


def test_capability_service_falls_back_when_claude_adapter_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingClaudeAdapter:
        def __init__(self, config: CapabilityProviderConfig, *, clock: Any = None) -> None:
            self.descriptor = CapabilityAdapterDescriptor(
                adapter_name="failing-claude-adapter",
                provider_family=CapabilityProviderFamily.CLAUDE,
                model=config.model,
                version=config.api_version or "2023-06-01",
                api_style="messages",
                supported_capabilities=[CapabilityName.SUMMARIZE],
            )

        def invoke(self, request: SummarizeRequest) -> SummarizeResponse:
            raise CapabilityAdapterError("claude transport failed")

    monkeypatch.setattr("mind.capabilities.service.ClaudeCapabilityAdapter", _FailingClaudeAdapter)
    service = CapabilityService(provider_config=_claude_config(), clock=_fixed_clock)

    response = service.summarize(
        SummarizeRequest(request_id="sum-claude-fallback", source_text="fallback source text")
    )

    assert response.trace.provider_family is CapabilityProviderFamily.DETERMINISTIC
    assert response.trace.fallback_used is True
    assert "claude transport failed" in str(response.trace.fallback_reason)


def test_capability_service_fail_closed_when_claude_adapter_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingClaudeAdapter:
        def __init__(self, config: CapabilityProviderConfig, *, clock: Any = None) -> None:
            self.descriptor = CapabilityAdapterDescriptor(
                adapter_name="failing-claude-adapter",
                provider_family=CapabilityProviderFamily.CLAUDE,
                model=config.model,
                version=config.api_version or "2023-06-01",
                api_style="messages",
                supported_capabilities=[CapabilityName.SUMMARIZE],
            )

        def invoke(self, request: SummarizeRequest) -> SummarizeResponse:
            raise CapabilityAdapterError("claude transport failed")

    monkeypatch.setattr("mind.capabilities.service.ClaudeCapabilityAdapter", _FailingClaudeAdapter)
    service = CapabilityService(provider_config=_claude_config(), clock=_fixed_clock)

    with pytest.raises(CapabilityServiceError, match="primary capability adapter failed for claude"):
        service.summarize(
            SummarizeRequest(
                request_id="sum-claude-fail-closed",
                source_text="provider source text",
                fallback_policy=CapabilityFallbackPolicy.FAIL_CLOSED,
            )
        )


def _claude_trace() -> CapabilityInvocationTrace:
    return CapabilityInvocationTrace(
        provider_family=CapabilityProviderFamily.CLAUDE,
        model="claude-3-7-sonnet",
        endpoint="https://api.anthropic.com/v1/messages",
        version="2023-06-01",
        started_at=_fixed_clock(),
        completed_at=_fixed_clock(),
        duration_ms=0,
    )
