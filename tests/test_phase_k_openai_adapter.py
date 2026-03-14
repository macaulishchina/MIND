from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from mind.capabilities import (
    AnswerRequest,
    AnswerResponse,
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
    OpenAICapabilityAdapter,
    ReflectRequest,
    ReflectResponse,
    SummarizeRequest,
    SummarizeResponse,
)


def _fixed_clock() -> datetime:
    return datetime(2026, 3, 11, 17, 0, tzinfo=UTC)


def _openai_config() -> CapabilityProviderConfig:
    return CapabilityProviderConfig(
        provider="openai",
        provider_family=CapabilityProviderFamily.OPENAI,
        model="gpt-4.1-mini",
        endpoint="https://api.openai.com/v1/responses",
        api_version="v1",
        timeout_ms=25_000,
        retry_policy="default",
        auth=CapabilityAuthConfig(
            mode="bearer_token",
            secret_env="OPENAI_API_KEY",
            secret_value="secret-key",
            parameter_name="Authorization",
        ),
    )


def test_openai_adapter_posts_structured_summary_request() -> None:
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
            "id": "resp_123",
            "status": "completed",
            "model": "gpt-4.1-mini",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps({"summary_text": "provider summary"}),
                        }
                    ],
                }
            ],
        }

    adapter = OpenAICapabilityAdapter(
        _openai_config(),
        clock=_fixed_clock,
        transport=_transport,
    )
    response = adapter.invoke(
        SummarizeRequest(
            request_id="sum-openai",
            source_text="source text for the provider summary",
            source_refs=["obj-1"],
            instruction="Summarize for handoff.",
            max_output_tokens=64,
        )
    )

    assert isinstance(response, SummarizeResponse)
    assert response.summary_text == "provider summary"
    assert response.source_refs == ["obj-1"]
    assert response.trace.provider_family is CapabilityProviderFamily.OPENAI
    assert captured["endpoint"] == "https://api.openai.com/v1/responses"
    assert captured["headers"]["Authorization"] == "Bearer secret-key"
    assert captured["payload"]["model"] == "gpt-4.1-mini"
    assert captured["payload"]["max_output_tokens"] == 64
    assert captured["payload"]["text"]["format"]["type"] == "json_schema"
    assert "Summarize for handoff." in captured["payload"]["input"]


def test_openai_adapter_parses_reflect_claims() -> None:
    adapter = OpenAICapabilityAdapter(
        _openai_config(),
        clock=_fixed_clock,
        transport=lambda *_args, **_kwargs: {
            "status": "completed",
            "model": "gpt-4.1-mini",
            "output_text": json.dumps(
                {
                    "reflection_text": "Episode failed; reflection focus: stale memory",
                    "claims": ["stale-memory", "refresh-summary"],
                }
            ),
        },
    )

    response = adapter.invoke(
        ReflectRequest(
            request_id="reflect-openai",
            focus="why it failed",
            evidence_text="stale memory caused repeated tool mismatch",
            episode_id="episode-004",
            evidence_refs=["episode-004", "episode-004-raw-04"],
            outcome_hint="failure",
        )
    )

    assert isinstance(response, ReflectResponse)
    assert response.reflection_text.startswith("Episode failed")
    assert response.claims == ["stale-memory", "refresh-summary"]
    assert response.evidence_refs == ["episode-004", "episode-004-raw-04"]


def test_openai_adapter_supports_chat_completions_compatible_endpoint() -> None:
    captured: dict[str, Any] = {}
    config = _openai_config().model_copy(update={"endpoint": "https://api.deepseek.com"})

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
            "id": "chatcmpl_123",
            "model": "deepseek-chat",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps({"summary_text": "compatible summary"}),
                    }
                }
            ],
        }

    adapter = OpenAICapabilityAdapter(
        config,
        clock=_fixed_clock,
        transport=_transport,
    )
    response = adapter.invoke(
        SummarizeRequest(
            request_id="sum-openai-compatible",
            source_text="source text for a compatible provider",
            source_refs=["obj-compatible"],
            instruction="Summarize for a compatible provider.",
            max_output_tokens=48,
        )
    )

    assert isinstance(response, SummarizeResponse)
    assert response.summary_text == "compatible summary"
    assert response.trace.provider_family is CapabilityProviderFamily.OPENAI
    assert response.trace.endpoint == "https://api.deepseek.com/chat/completions"
    assert captured["endpoint"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer secret-key"
    assert captured["payload"]["messages"][0]["role"] == "user"
    assert "Return JSON only." in captured["payload"]["messages"][0]["content"]
    assert captured["payload"]["max_tokens"] == 48


def test_openai_adapter_extracts_json_from_markdown_code_fence() -> None:
    adapter = OpenAICapabilityAdapter(
        _openai_config(),
        clock=_fixed_clock,
        transport=lambda *_args, **_kwargs: {
            "status": "completed",
            "model": "gpt-4.1-mini",
            "output_text": '```json\n{"summary_text":"fenced summary"}\n```',
        },
    )

    response = adapter.invoke(SummarizeRequest(request_id="sum-fenced", source_text="source"))

    assert isinstance(response, SummarizeResponse)
    assert response.summary_text == "fenced summary"


def test_openai_adapter_projects_plain_text_answer_when_provider_skips_json() -> None:
    config = _openai_config().model_copy(update={"endpoint": "https://api.deepseek.com"})
    adapter = OpenAICapabilityAdapter(
        config,
        clock=_fixed_clock,
        transport=lambda *_args, **_kwargs: {
            "id": "chatcmpl_plain_answer",
            "model": "deepseek-chat",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "这是来自兼容服务的自然语言回答。",
                    }
                }
            ],
        },
    )

    response = adapter.invoke(
        AnswerRequest(
            request_id="answer-openai-plain-text",
            question="请给出简短回答",
            context_text="plain text compatible output",
            support_ids=["obj-plain"],
        )
    )

    assert isinstance(response, AnswerResponse)
    assert response.answer_text == "这是来自兼容服务的自然语言回答。"
    assert response.support_ids == ["obj-plain"]


def test_openai_adapter_accepts_answer_alias_in_json_payload() -> None:
    config = _openai_config().model_copy(update={"endpoint": "https://api.deepseek.com"})
    adapter = OpenAICapabilityAdapter(
        config,
        clock=_fixed_clock,
        transport=lambda *_args, **_kwargs: {
            "id": "chatcmpl_answer_alias",
            "model": "deepseek-chat",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"answer":"这是兼容服务返回的 answer 字段。"}',
                    }
                }
            ],
        },
    )

    response = adapter.invoke(
        AnswerRequest(
            request_id="answer-openai-answer-alias",
            question="请给出简短回答",
            context_text="json alias output",
            support_ids=["obj-alias"],
        )
    )

    assert isinstance(response, AnswerResponse)
    assert response.answer_text == "这是兼容服务返回的 answer 字段。"
    assert response.support_ids == ["obj-alias"]


def test_openai_adapter_captures_raw_exchange_for_answer_requests() -> None:
    config = _openai_config().model_copy(update={"endpoint": "https://api.deepseek.com"})
    adapter = OpenAICapabilityAdapter(
        config,
        clock=_fixed_clock,
        transport=lambda *_args, **_kwargs: {
            "id": "chatcmpl_answer_trace",
            "model": "deepseek-chat",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"answer_text":"你好，我是 DeepSeek。"}',
                    }
                }
            ],
        },
    )

    response = adapter.invoke(
        AnswerRequest(
            request_id="answer-openai-trace",
            question="你好",
            context_text='{"kind":"workspace","slots":[{"summary":"你好，今天下雨。"}]}',
            support_ids=["obj-1"],
            capture_raw_exchange=True,
        )
    )

    assert isinstance(response, AnswerResponse)
    assert response.answer_text == "你好，我是 DeepSeek。"
    assert response.trace.request_text is not None
    assert "Question: 你好" in response.trace.request_text
    assert response.trace.response_text == '{"answer_text":"你好，我是 DeepSeek。"}'


def test_openai_adapter_rejects_empty_payload() -> None:
    adapter = OpenAICapabilityAdapter(
        _openai_config(),
        clock=_fixed_clock,
        transport=lambda *_args, **_kwargs: {
            "status": "completed",
            "model": "gpt-4.1-mini",
            "output_text": "   ",
        },
    )

    with pytest.raises(CapabilityAdapterError, match="valid JSON output"):
        adapter.invoke(SummarizeRequest(request_id="sum-invalid", source_text="source"))


def test_capability_service_builds_openai_adapter_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, SummarizeRequest] = {}

    class _FakeOpenAIAdapter:
        def __init__(
            self,
            config: CapabilityProviderConfig,
            *,
            clock: Any = None,
            transport: Any = None,
        ) -> None:
            self.descriptor = CapabilityAdapterDescriptor(
                adapter_name="fake-openai-adapter",
                provider_family=CapabilityProviderFamily.OPENAI,
                model=config.model,
                version=config.api_version or "v1",
                api_style="responses",
                supported_capabilities=list(CapabilityName),
            )

        def invoke(self, request: SummarizeRequest) -> SummarizeResponse:
            captured["request"] = request
            return SummarizeResponse(
                summary_text="openai adapter response",
                source_refs=list(request.source_refs),
                trace=_openai_trace(),
            )

    monkeypatch.setattr("mind.capabilities.service.OpenAICapabilityAdapter", _FakeOpenAIAdapter)
    service = CapabilityService(provider_config=_openai_config(), clock=_fixed_clock)

    response = service.summarize(
        SummarizeRequest(
            request_id="sum-service-openai",
            source_text="provider source text",
            source_refs=["obj-7"],
        )
    )

    assert captured["request"].source_refs == ["obj-7"]
    assert isinstance(response, SummarizeResponse)
    assert response.summary_text == "openai adapter response"
    assert response.trace.provider_family is CapabilityProviderFamily.OPENAI


def test_capability_service_falls_back_when_openai_adapter_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingOpenAIAdapter:
        def __init__(self, config: CapabilityProviderConfig, *, clock: Any = None) -> None:
            self.descriptor = CapabilityAdapterDescriptor(
                adapter_name="failing-openai-adapter",
                provider_family=CapabilityProviderFamily.OPENAI,
                model=config.model,
                version=config.api_version or "v1",
                api_style="responses",
                supported_capabilities=[CapabilityName.SUMMARIZE],
            )

        def invoke(self, request: SummarizeRequest) -> SummarizeResponse:
            raise CapabilityAdapterError("provider transport failed")

    monkeypatch.setattr("mind.capabilities.service.OpenAICapabilityAdapter", _FailingOpenAIAdapter)
    service = CapabilityService(provider_config=_openai_config(), clock=_fixed_clock)

    response = service.summarize(
        SummarizeRequest(request_id="sum-openai-fallback", source_text="fallback source text")
    )

    assert response.trace.provider_family is CapabilityProviderFamily.DETERMINISTIC
    assert response.trace.fallback_used is True
    assert "provider transport failed" in str(response.trace.fallback_reason)


def test_capability_service_fail_closed_when_openai_adapter_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingOpenAIAdapter:
        def __init__(self, config: CapabilityProviderConfig, *, clock: Any = None) -> None:
            self.descriptor = CapabilityAdapterDescriptor(
                adapter_name="failing-openai-adapter",
                provider_family=CapabilityProviderFamily.OPENAI,
                model=config.model,
                version=config.api_version or "v1",
                api_style="responses",
                supported_capabilities=[CapabilityName.SUMMARIZE],
            )

        def invoke(self, request: SummarizeRequest) -> SummarizeResponse:
            raise CapabilityAdapterError("provider transport failed")

    monkeypatch.setattr("mind.capabilities.service.OpenAICapabilityAdapter", _FailingOpenAIAdapter)
    service = CapabilityService(provider_config=_openai_config(), clock=_fixed_clock)

    with pytest.raises(
        CapabilityServiceError, match="primary capability adapter failed for openai"
    ):
        service.summarize(
            SummarizeRequest(
                request_id="sum-openai-fail-closed",
                source_text="provider source text",
                fallback_policy=CapabilityFallbackPolicy.FAIL_CLOSED,
            )
        )


def _openai_trace() -> CapabilityInvocationTrace:
    return CapabilityInvocationTrace(
        provider_family=CapabilityProviderFamily.OPENAI,
        model="gpt-4.1-mini",
        endpoint="https://api.openai.com/v1/responses",
        version="v1",
        started_at=_fixed_clock(),
        completed_at=_fixed_clock(),
        duration_ms=0,
    )
