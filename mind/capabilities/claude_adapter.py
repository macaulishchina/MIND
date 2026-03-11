"""Anthropic Messages API adapter for Phase K capabilities."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .adapter import CapabilityAdapterDescriptor, CapabilityAdapterError
from .config import CapabilityAuthMode, CapabilityProviderConfig
from .contracts import (
    AnswerRequest,
    AnswerResponse,
    CapabilityInvocationTrace,
    CapabilityName,
    CapabilityProviderFamily,
    CapabilityRequest,
    CapabilityResponse,
    OfflineReconstructRequest,
    OfflineReconstructResponse,
    ReflectRequest,
    ReflectResponse,
    SummarizeRequest,
    SummarizeResponse,
)

type MessagesTransport = Callable[
    [str, dict[str, Any], dict[str, str], float | None],
    dict[str, Any],
]


class ClaudeCapabilityAdapter:
    """Execute capability calls through the Anthropic Messages API."""

    def __init__(
        self,
        config: CapabilityProviderConfig,
        *,
        clock: Callable[[], datetime] | None = None,
        transport: MessagesTransport | None = None,
    ) -> None:
        if config.provider_family is not CapabilityProviderFamily.CLAUDE:
            raise ValueError("ClaudeCapabilityAdapter requires provider_family=claude")
        if config.auth.mode != CapabilityAuthMode.API_KEY:
            raise ValueError("Claude adapter requires api key auth mode")
        if not config.auth.is_configured():
            raise ValueError("Claude adapter requires configured auth")
        self._config = config
        self._clock = clock or _utc_now
        self._transport = transport or _default_transport
        self.descriptor = CapabilityAdapterDescriptor(
            adapter_name="claude-capability-adapter",
            provider_family=CapabilityProviderFamily.CLAUDE,
            model=config.model,
            version=config.api_version or "2023-06-01",
            api_style="messages",
            supported_capabilities=list(CapabilityName),
        )

    def invoke(self, request: CapabilityRequest) -> CapabilityResponse:
        started_at = self._clock()
        payload = _request_payload(request, self._config.model)
        response_payload = self._transport(
            self._config.endpoint,
            payload,
            _headers(self._config),
            self._config.timeout_ms / 1000.0,
        )
        completed_at = self._clock()
        trace = CapabilityInvocationTrace(
            provider_family=CapabilityProviderFamily.CLAUDE,
            model=str(response_payload.get("model", self._config.model)),
            endpoint=self._config.endpoint,
            version=self.descriptor.version,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=max(0, int((completed_at - started_at).total_seconds() * 1000)),
        )
        return _parse_response(request, response_payload, trace)


def _request_payload(request: CapabilityRequest, model: str) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": _max_tokens_for_request(request),
        "messages": [
            {
                "role": "user",
                "content": _prompt_for_request(request),
            }
        ],
    }


def _headers(config: CapabilityProviderConfig) -> dict[str, str]:
    secret_value = config.auth.secret_value
    if not secret_value:
        raise CapabilityAdapterError("Claude auth secret is not configured")
    return {
        "x-api-key": secret_value,
        "anthropic-version": config.api_version or "2023-06-01",
        "content-type": "application/json",
    }


def _prompt_for_request(request: CapabilityRequest) -> str:
    if isinstance(request, SummarizeRequest):
        instruction = request.instruction or "Produce a concise operator-grade summary."
        return (
            "You are the MIND summarize capability.\n"
            "Return JSON only with key summary_text.\n"
            f"Instruction: {instruction}\n"
            f"Source refs: {json.dumps(request.source_refs, ensure_ascii=True)}\n"
            "Source text:\n"
            f"{request.source_text}"
        )
    if isinstance(request, ReflectRequest):
        return (
            "You are the MIND reflect capability.\n"
            "Return JSON only with keys reflection_text and claims.\n"
            f"Focus: {_stringify_focus(request.focus)}\n"
            f"Episode id: {request.episode_id or '-'}\n"
            f"Outcome hint: {request.outcome_hint or '-'}\n"
            f"Evidence refs: {json.dumps(request.evidence_refs, ensure_ascii=True)}\n"
            "Evidence text:\n"
            f"{request.evidence_text}"
        )
    if isinstance(request, AnswerRequest):
        return (
            "You are the MIND answer capability.\n"
            "Return JSON only with key answer_text.\n"
            f"Question: {request.question}\n"
            f"Hard constraints: {json.dumps(request.hard_constraints, ensure_ascii=True)}\n"
            f"Support ids: {json.dumps(request.support_ids, ensure_ascii=True)}\n"
            "Context text:\n"
            f"{request.context_text}"
        )
    if isinstance(request, OfflineReconstructRequest):
        return (
            "You are the MIND offline reconstruction capability.\n"
            "Return JSON only with key reconstruction_text.\n"
            f"Objective: {request.objective}\n"
            f"Supporting episodes: {json.dumps(request.episode_ids, ensure_ascii=True)}\n"
            f"Evidence refs: {json.dumps(request.evidence_refs, ensure_ascii=True)}\n"
            "Evidence text:\n"
            f"{request.evidence_text}"
        )
    raise CapabilityAdapterError(f"unsupported request type {type(request).__name__}")


def _max_tokens_for_request(request: CapabilityRequest) -> int:
    if isinstance(request, SummarizeRequest) and request.max_output_tokens is not None:
        return request.max_output_tokens
    if isinstance(request, AnswerRequest) and request.max_answer_tokens is not None:
        return request.max_answer_tokens
    return 512


def _parse_response(
    request: CapabilityRequest,
    response_payload: dict[str, Any],
    trace: CapabilityInvocationTrace,
) -> CapabilityResponse:
    output_text = _extract_output_text(response_payload)
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise CapabilityAdapterError("claude response did not contain valid JSON output") from exc

    if isinstance(request, SummarizeRequest):
        return SummarizeResponse(
            summary_text=str(payload["summary_text"]),
            source_refs=list(request.source_refs),
            trace=trace,
        )
    if isinstance(request, ReflectRequest):
        return ReflectResponse(
            reflection_text=str(payload["reflection_text"]),
            claims=[str(item) for item in payload.get("claims", [])],
            evidence_refs=list(request.evidence_refs),
            trace=trace,
        )
    if isinstance(request, AnswerRequest):
        return AnswerResponse(
            answer_text=str(payload["answer_text"]),
            support_ids=list(request.support_ids),
            trace=trace,
        )
    if isinstance(request, OfflineReconstructRequest):
        return OfflineReconstructResponse(
            reconstruction_text=str(payload["reconstruction_text"]),
            supporting_episode_ids=list(request.episode_ids),
            evidence_refs=list(request.evidence_refs),
            trace=trace,
        )
    raise CapabilityAdapterError(f"unsupported request type {type(request).__name__}")


def _extract_output_text(response_payload: dict[str, Any]) -> str:
    content = response_payload.get("content", [])
    for item in content:
        if item.get("type") != "text":
            continue
        text = item.get("text")
        if isinstance(text, str) and text:
            return text
    raise CapabilityAdapterError("claude response did not contain text content")


def _default_transport(
    endpoint: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: float | None,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise CapabilityAdapterError(
            f"claude request failed with status {exc.code}: {detail}"
        ) from exc
    except URLError as exc:
        raise CapabilityAdapterError(f"claude request failed: {exc.reason}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CapabilityAdapterError("claude response was not valid JSON") from exc


def _stringify_focus(focus: str | dict[str, Any]) -> str:
    if isinstance(focus, str):
        return focus
    return json.dumps(focus, ensure_ascii=True, sort_keys=True)


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)
