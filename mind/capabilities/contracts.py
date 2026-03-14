"""Typed contracts for the Phase K capability layer."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CapabilityModel(BaseModel):
    """Strict base model shared by capability contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class CapabilityName(StrEnum):
    SUMMARIZE = "summarize"
    REFLECT = "reflect"
    ANSWER = "answer"
    OFFLINE_RECONSTRUCT = "offline_reconstruct"


CAPABILITY_CATALOG: tuple[CapabilityName, ...] = (
    CapabilityName.SUMMARIZE,
    CapabilityName.REFLECT,
    CapabilityName.ANSWER,
    CapabilityName.OFFLINE_RECONSTRUCT,
)


class CapabilityProviderFamily(StrEnum):
    DETERMINISTIC = "deterministic"
    OPENAI = "openai"
    CLAUDE = "claude"
    GEMINI = "gemini"


class CapabilityFallbackPolicy(StrEnum):
    ALLOW_DETERMINISTIC = "allow_deterministic"
    FAIL_CLOSED = "fail_closed"


class CapabilityInvocationTrace(CapabilityModel):
    """Trace fields that every capability call must record."""

    provider_family: CapabilityProviderFamily
    model: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    version: str = Field(min_length=1)
    started_at: datetime
    completed_at: datetime
    duration_ms: int = Field(ge=0)
    fallback_used: bool = False
    fallback_reason: str | None = None
    request_text: str | None = None
    response_text: str | None = None

    @model_validator(mode="after")
    def require_fallback_reason(self) -> CapabilityInvocationTrace:
        if self.fallback_used and not self.fallback_reason:
            raise ValueError("fallback_reason required when fallback_used is true")
        return self


class CapabilityRequestBase(CapabilityModel):
    request_id: str = Field(min_length=1)
    fallback_policy: CapabilityFallbackPolicy = CapabilityFallbackPolicy.ALLOW_DETERMINISTIC


class CapabilityResponseBase(CapabilityModel):
    trace: CapabilityInvocationTrace


class SummarizeRequest(CapabilityRequestBase):
    capability: Literal[CapabilityName.SUMMARIZE] = CapabilityName.SUMMARIZE
    source_text: str = Field(min_length=1)
    source_refs: list[str] = Field(default_factory=list)
    instruction: str | None = None
    max_output_tokens: int | None = Field(default=None, ge=1)


class SummarizeResponse(CapabilityResponseBase):
    capability: Literal[CapabilityName.SUMMARIZE] = CapabilityName.SUMMARIZE
    summary_text: str = Field(min_length=1)
    source_refs: list[str] = Field(default_factory=list)


class ReflectRequest(CapabilityRequestBase):
    capability: Literal[CapabilityName.REFLECT] = CapabilityName.REFLECT
    focus: str | dict[str, Any]
    evidence_text: str = Field(min_length=1)
    episode_id: str | None = None
    outcome_hint: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class ReflectResponse(CapabilityResponseBase):
    capability: Literal[CapabilityName.REFLECT] = CapabilityName.REFLECT
    reflection_text: str = Field(min_length=1)
    claims: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class AnswerRequest(CapabilityRequestBase):
    capability: Literal[CapabilityName.ANSWER] = CapabilityName.ANSWER
    question: str = Field(min_length=1)
    context_text: str = Field(min_length=1)
    support_ids: list[str] = Field(default_factory=list)
    hard_constraints: list[str] = Field(default_factory=list)
    max_answer_tokens: int | None = Field(default=None, ge=1)
    capture_raw_exchange: bool = False


class AnswerResponse(CapabilityResponseBase):
    capability: Literal[CapabilityName.ANSWER] = CapabilityName.ANSWER
    answer_text: str = Field(min_length=1)
    support_ids: list[str] = Field(default_factory=list)


class OfflineReconstructRequest(CapabilityRequestBase):
    capability: Literal[CapabilityName.OFFLINE_RECONSTRUCT] = CapabilityName.OFFLINE_RECONSTRUCT
    objective: str = Field(min_length=1)
    evidence_text: str = Field(min_length=1)
    episode_ids: list[str] = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)


class OfflineReconstructResponse(CapabilityResponseBase):
    capability: Literal[CapabilityName.OFFLINE_RECONSTRUCT] = CapabilityName.OFFLINE_RECONSTRUCT
    reconstruction_text: str = Field(min_length=1)
    supporting_episode_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


type CapabilityRequest = (
    SummarizeRequest | ReflectRequest | AnswerRequest | OfflineReconstructRequest
)
type CapabilityResponse = (
    SummarizeResponse | ReflectResponse | AnswerResponse | OfflineReconstructResponse
)


class CapabilityRoutingConfig(CapabilityModel):
    """Per-capability model routing overrides (Phase γ-3).

    Maps individual :class:`CapabilityName` values to distinct
    :class:`CapabilityProviderConfig` instances.  When a capability is invoked
    via :meth:`CapabilityService.invoke`, the service first checks this routing
    table; if a match is found the specified provider is used instead of the
    global default.

    Example::

        routing = CapabilityRoutingConfig(routes={
            CapabilityName.SUMMARIZE: small_model_config,
            CapabilityName.ANSWER: large_model_config,
        })
        service = CapabilityService(routing_config=routing)
    """

    routes: dict[CapabilityName, Any] = Field(default_factory=dict)


_REQUEST_MODELS = {
    CapabilityName.SUMMARIZE: SummarizeRequest,
    CapabilityName.REFLECT: ReflectRequest,
    CapabilityName.ANSWER: AnswerRequest,
    CapabilityName.OFFLINE_RECONSTRUCT: OfflineReconstructRequest,
}

_RESPONSE_MODELS = {
    CapabilityName.SUMMARIZE: SummarizeResponse,
    CapabilityName.REFLECT: ReflectResponse,
    CapabilityName.ANSWER: AnswerResponse,
    CapabilityName.OFFLINE_RECONSTRUCT: OfflineReconstructResponse,
}


def request_model_for(capability: CapabilityName) -> type[CapabilityRequest]:
    """Return the request model type for one capability."""

    return _REQUEST_MODELS[capability]  # type: ignore[return-value]


def response_model_for(capability: CapabilityName) -> type[CapabilityResponse]:
    """Return the response model type for one capability."""

    return _RESPONSE_MODELS[capability]  # type: ignore[return-value]
