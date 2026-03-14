"""Unified capability service with deterministic fallback support."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from os import environ
from typing import Any

from .adapter import (
    CapabilityAdapter,
    CapabilityAdapterDescriptor,
    CapabilityAdapterError,
    invoke_capability,
)
from .claude_adapter import ClaudeCapabilityAdapter
from .config import CapabilityProviderConfig, resolve_capability_provider_config
from .contracts import (
    AnswerRequest,
    AnswerResponse,
    CapabilityFallbackPolicy,
    CapabilityInvocationTrace,
    CapabilityName,
    CapabilityProviderFamily,
    CapabilityRequest,
    CapabilityResponse,
    CapabilityRoutingConfig,
    OfflineReconstructRequest,
    OfflineReconstructResponse,
    ReflectRequest,
    ReflectResponse,
    SummarizeRequest,
    SummarizeResponse,
)
from .gemini_adapter import GeminiCapabilityAdapter
from .openai_adapter import OpenAICapabilityAdapter


class CapabilityServiceError(RuntimeError):
    """Raised when a capability call cannot complete safely."""


class DeterministicCapabilityAdapter:
    """Deterministic baseline adapter for all Phase K capabilities."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or _utc_now
        self.descriptor = CapabilityAdapterDescriptor(
            adapter_name="deterministic-capability-adapter",
            provider_family=CapabilityProviderFamily.DETERMINISTIC,
            model="deterministic",
            version="deterministic-v1",
            api_style="deterministic",
            supported_capabilities=list(CapabilityName),
        )

    def invoke(self, request: CapabilityRequest) -> CapabilityResponse:
        trace = self._trace()
        if isinstance(request, SummarizeRequest):
            return SummarizeResponse(
                summary_text=_excerpt(request.source_text, limit=24),
                source_refs=list(request.source_refs),
                trace=trace,
            )
        if isinstance(request, ReflectRequest):
            focus = _stringify_focus(request.focus)
            claims = _reflection_claims(request.evidence_text)
            reflection_text = f"{focus}: {_excerpt(request.evidence_text, limit=20)}"
            if request.outcome_hint in {"success", "failure"}:
                prefix = (
                    "Episode succeeded" if request.outcome_hint == "success" else "Episode failed"
                )
                reflection_text = f"{prefix}; reflection focus: {focus[:120]}"
            return ReflectResponse(
                reflection_text=reflection_text,
                claims=claims,
                evidence_refs=list(request.evidence_refs),
                trace=trace,
            )
        if isinstance(request, AnswerRequest):
            answer = _deterministic_answer(request)
            return AnswerResponse(
                answer_text=answer,
                support_ids=list(request.support_ids),
                trace=trace,
            )
        if isinstance(request, OfflineReconstructRequest):
            return OfflineReconstructResponse(
                reconstruction_text=(
                    f"{request.objective}: {_excerpt(request.evidence_text, limit=26)}"
                ),
                supporting_episode_ids=list(request.episode_ids),
                evidence_refs=list(request.evidence_refs),
                trace=trace,
            )
        raise CapabilityServiceError(f"unsupported request type {type(request).__name__}")

    def _trace(self) -> CapabilityInvocationTrace:
        started_at = self._clock()
        completed_at = self._clock()
        return CapabilityInvocationTrace(
            provider_family=CapabilityProviderFamily.DETERMINISTIC,
            model=self.descriptor.model,
            endpoint="local://deterministic",
            version=self.descriptor.version,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=max(0, int((completed_at - started_at).total_seconds() * 1000)),
        )


class CapabilityService:
    """Single capability dispatch surface used by Phase K callers."""

    def __init__(
        self,
        *,
        provider_config: CapabilityProviderConfig | None = None,
        adapters: list[CapabilityAdapter] | None = None,
        clock: Callable[[], datetime] | None = None,
        routing_config: CapabilityRoutingConfig | None = None,
    ) -> None:
        self._clock = clock or _utc_now
        self.provider_config = provider_config or resolve_capability_provider_config()
        self._routing_config = routing_config
        deterministic_adapter = DeterministicCapabilityAdapter(clock=self._clock)
        adapter_list = [
            deterministic_adapter,
            *_default_provider_adapters(self.provider_config, clock=self._clock),
            *(adapters or []),
        ]
        self._adapters = {adapter.descriptor.provider_family: adapter for adapter in adapter_list}

    def invoke(self, request: CapabilityRequest) -> CapabilityResponse:
        # Check per-capability routing override (Phase γ-3).
        if self._routing_config is not None:
            capability = getattr(request, "capability", None)
            if capability is not None and capability in self._routing_config.routes:
                routed_config = self._routing_config.routes[capability]
                return self._invoke(request, provider_config=routed_config)
        return self._invoke(request, provider_config=None)

    def _invoke(
        self,
        request: CapabilityRequest,
        *,
        provider_config: CapabilityProviderConfig | None,
    ) -> CapabilityResponse:
        active_provider_config = provider_config or self.provider_config
        primary = self._resolve_primary_adapter(active_provider_config)
        if primary is not None:
            try:
                return invoke_capability(primary, request)
            except (CapabilityAdapterError, OSError, TimeoutError, ValueError) as exc:
                return self._handle_primary_failure(
                    request,
                    exc,
                    provider_config=active_provider_config,
                )

        if request.fallback_policy is CapabilityFallbackPolicy.ALLOW_DETERMINISTIC:
            fallback = self._adapters[CapabilityProviderFamily.DETERMINISTIC]
            response = invoke_capability(fallback, request)
            return response.model_copy(
                update={
                    "trace": response.trace.model_copy(
                        update={
                            "fallback_used": True,
                            "fallback_reason": (
                                "primary adapter unavailable for "
                                f"{active_provider_config.provider_family.value}"
                            ),
                        }
                    )
                }
            )

        raise CapabilityServiceError(
            "primary capability adapter unavailable for "
            f"{active_provider_config.provider_family.value}"
        )

    def _handle_primary_failure(
        self,
        request: CapabilityRequest,
        exc: Exception,
        *,
        provider_config: CapabilityProviderConfig,
    ) -> CapabilityResponse:
        if (
            request.fallback_policy is CapabilityFallbackPolicy.ALLOW_DETERMINISTIC
            and provider_config.provider_family is not CapabilityProviderFamily.DETERMINISTIC
        ):
            fallback = self._adapters[CapabilityProviderFamily.DETERMINISTIC]
            response = invoke_capability(fallback, request)
            return response.model_copy(
                update={
                    "trace": response.trace.model_copy(
                        update={
                            "fallback_used": True,
                            "fallback_reason": (
                                "primary adapter failed for "
                                f"{provider_config.provider_family.value}: {exc}"
                            ),
                        }
                    )
                }
            )
        raise CapabilityServiceError(
            f"primary capability adapter failed for {provider_config.provider_family.value}: {exc}"
        ) from exc

    def summarize(
        self,
        request: SummarizeRequest,
        *,
        provider_config: CapabilityProviderConfig | None = None,
    ) -> SummarizeResponse:
        response = self._invoke(request, provider_config=provider_config)
        if not isinstance(response, SummarizeResponse):
            raise CapabilityServiceError("summarize returned unexpected response type")
        return response

    def reflect(
        self,
        request: ReflectRequest,
        *,
        provider_config: CapabilityProviderConfig | None = None,
    ) -> ReflectResponse:
        response = self._invoke(request, provider_config=provider_config)
        if not isinstance(response, ReflectResponse):
            raise CapabilityServiceError("reflect returned unexpected response type")
        return response

    def answer(
        self,
        request: AnswerRequest,
        *,
        provider_config: CapabilityProviderConfig | None = None,
    ) -> AnswerResponse:
        response = self._invoke(request, provider_config=provider_config)
        if not isinstance(response, AnswerResponse):
            raise CapabilityServiceError("answer returned unexpected response type")
        return response

    def offline_reconstruct(
        self,
        request: OfflineReconstructRequest,
        *,
        provider_config: CapabilityProviderConfig | None = None,
    ) -> OfflineReconstructResponse:
        response = self._invoke(request, provider_config=provider_config)
        if not isinstance(response, OfflineReconstructResponse):
            raise CapabilityServiceError("offline_reconstruct returned unexpected response type")
        return response

    def _resolve_primary_adapter(
        self,
        provider_config: CapabilityProviderConfig,
    ) -> CapabilityAdapter | None:
        if provider_config.provider_family is CapabilityProviderFamily.DETERMINISTIC:
            return self._adapters.get(CapabilityProviderFamily.DETERMINISTIC)
        if provider_config.model_dump(mode="json") == self.provider_config.model_dump(mode="json"):
            return self._adapters.get(provider_config.provider_family)
        return _build_primary_adapter(provider_config, clock=self._clock)


def build_capability_adapters_from_environment(
    *,
    provider_families: Sequence[CapabilityProviderFamily] | None = None,
    env: Mapping[str, str] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> list[CapabilityAdapter]:
    """Build external provider adapters from an environment-style config mapping."""

    active_clock = clock or _utc_now
    active_env = dict(environ if env is None else env)
    adapters: list[CapabilityAdapter] = []
    families = tuple(provider_families or _external_provider_families())
    adapter_builders = {
        CapabilityProviderFamily.OPENAI: OpenAICapabilityAdapter,
        CapabilityProviderFamily.CLAUDE: ClaudeCapabilityAdapter,
        CapabilityProviderFamily.GEMINI: GeminiCapabilityAdapter,
    }
    for family in families:
        if family is CapabilityProviderFamily.DETERMINISTIC:
            continue
        provider_env = dict(active_env)
        provider_env["MIND_PROVIDER"] = family.value
        config = resolve_capability_provider_config(env=provider_env)
        if not config.auth.is_configured():
            continue
        adapter: CapabilityAdapter = adapter_builders[family](config, clock=active_clock)  # type: ignore[assignment]
        adapters.append(adapter)
    return adapters


def _deterministic_answer(request: AnswerRequest) -> str:
    normalized_constraints = {constraint.lower() for constraint in request.hard_constraints}
    if "must answer with only success or failure" in normalized_constraints:
        lowered = request.context_text.lower()
        if "failure" in lowered and "success" not in lowered:
            return "failure"
        return "success" if "success" in lowered else "failure"
    return _excerpt(request.context_text, limit=24)


def _reflection_claims(evidence_text: str) -> list[str]:
    words = [word for word in evidence_text.split() if word]
    if not words:
        return []
    if len(words) <= 6:
        return [" ".join(words)]
    midpoint = max(1, min(len(words) - 1, len(words) // 2))
    return [
        " ".join(words[:midpoint]),
        " ".join(words[midpoint : midpoint + max(1, min(6, len(words) - midpoint))]),
    ]


def _stringify_focus(focus: str | dict[str, Any]) -> str:
    if isinstance(focus, str):
        return focus
    return json.dumps(focus, ensure_ascii=True, sort_keys=True)


def _excerpt(text: str, *, limit: int) -> str:
    words = text.split()
    if not words:
        return ""
    excerpt = " ".join(words[:limit])
    return excerpt if excerpt else text[:160]


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _default_provider_adapters(
    provider_config: CapabilityProviderConfig,
    *,
    clock: Callable[[], datetime],
) -> list[CapabilityAdapter]:
    primary = _build_primary_adapter(provider_config, clock=clock)
    return [primary] if primary is not None else []


def _build_primary_adapter(
    provider_config: CapabilityProviderConfig,
    *,
    clock: Callable[[], datetime],
) -> CapabilityAdapter | None:
    if (
        provider_config.provider_family is CapabilityProviderFamily.OPENAI
        and provider_config.auth.is_configured()
    ):
        return OpenAICapabilityAdapter(provider_config, clock=clock)
    if (
        provider_config.provider_family is CapabilityProviderFamily.CLAUDE
        and provider_config.auth.is_configured()
    ):
        return ClaudeCapabilityAdapter(provider_config, clock=clock)
    if (
        provider_config.provider_family is CapabilityProviderFamily.GEMINI
        and provider_config.auth.is_configured()
    ):
        return GeminiCapabilityAdapter(provider_config, clock=clock)
    return None


def _external_provider_families() -> tuple[CapabilityProviderFamily, ...]:
    return (
        CapabilityProviderFamily.OPENAI,
        CapabilityProviderFamily.CLAUDE,
        CapabilityProviderFamily.GEMINI,
    )
