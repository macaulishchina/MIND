"""CapabilityAdapterBench v1 fixtures for Phase K."""

from __future__ import annotations

from dataclasses import dataclass

from mind.capabilities import (
    AnswerRequest,
    AnswerResponse,
    CapabilityFallbackPolicy,
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


@dataclass(frozen=True)
class CapabilityAdapterScenario:
    """One frozen adapter-bench scenario."""

    scenario_id: str
    capability: CapabilityName
    provider_family: CapabilityProviderFamily
    request: CapabilityRequest
    expected_response_type: type[CapabilityResponse]
    summary: str

    def __post_init__(self) -> None:
        if self.request.capability is not self.capability:
            raise RuntimeError(
                f"scenario {self.scenario_id} request capability "
                f"{self.request.capability.value} != {self.capability.value}"
            )


def build_capability_adapter_bench_v1() -> tuple[CapabilityAdapterScenario, ...]:
    """Return the frozen CapabilityAdapterBench v1 fixture set."""

    scenarios: list[CapabilityAdapterScenario] = []
    providers = (
        CapabilityProviderFamily.DETERMINISTIC,
        CapabilityProviderFamily.OPENAI,
        CapabilityProviderFamily.CLAUDE,
        CapabilityProviderFamily.GEMINI,
    )

    for provider in providers:
        scenarios.extend(_summarize_cases(provider))
        scenarios.extend(_reflect_cases(provider))
        scenarios.extend(_answer_cases(provider))
        scenarios.extend(_offline_reconstruct_cases(provider))

    if len(scenarios) != 48:
        raise RuntimeError(f"CapabilityAdapterBench v1 expected 48 scenarios, got {len(scenarios)}")
    return tuple(scenarios)


def _summarize_cases(
    provider: CapabilityProviderFamily,
) -> tuple[CapabilityAdapterScenario, ...]:
    prefix = f"{provider.value}_summarize"
    return (
        CapabilityAdapterScenario(
            scenario_id=f"{prefix}_basic",
            capability=CapabilityName.SUMMARIZE,
            provider_family=provider,
            request=SummarizeRequest(
                request_id=f"{prefix}_basic",
                source_text="alpha incident summary source",
            ),
            expected_response_type=SummarizeResponse,
            summary="Basic summary generation path.",
        ),
        CapabilityAdapterScenario(
            scenario_id=f"{prefix}_refs",
            capability=CapabilityName.SUMMARIZE,
            provider_family=provider,
            request=SummarizeRequest(
                request_id=f"{prefix}_refs",
                source_text="beta source text for constrained summary",
                source_refs=["obj-1", "obj-2"],
                instruction="Summarize for operator handoff.",
                max_output_tokens=48,
            ),
            expected_response_type=SummarizeResponse,
            summary="Summary with refs and explicit instruction.",
        ),
        CapabilityAdapterScenario(
            scenario_id=f"{prefix}_fail_closed",
            capability=CapabilityName.SUMMARIZE,
            provider_family=provider,
            request=SummarizeRequest(
                request_id=f"{prefix}_fail_closed",
                source_text="gamma source text requiring primary provider output",
                fallback_policy=CapabilityFallbackPolicy.FAIL_CLOSED,
            ),
            expected_response_type=SummarizeResponse,
            summary="Summary request that forbids deterministic fallback.",
        ),
    )


def _reflect_cases(
    provider: CapabilityProviderFamily,
) -> tuple[CapabilityAdapterScenario, ...]:
    prefix = f"{provider.value}_reflect"
    return (
        CapabilityAdapterScenario(
            scenario_id=f"{prefix}_basic",
            capability=CapabilityName.REFLECT,
            provider_family=provider,
            request=ReflectRequest(
                request_id=f"{prefix}_basic",
                focus="why the operation failed",
                evidence_text="deployment failed after timeout and retry exhaustion",
                episode_id="episode-001",
            ),
            expected_response_type=ReflectResponse,
            summary="Basic reflection against one episode.",
        ),
        CapabilityAdapterScenario(
            scenario_id=f"{prefix}_structured_focus",
            capability=CapabilityName.REFLECT,
            provider_family=provider,
            request=ReflectRequest(
                request_id=f"{prefix}_structured_focus",
                focus={"goal": "derive lessons", "scope": "incident review"},
                evidence_text="worker retried twice before circuit breaker opened",
                evidence_refs=["raw-1", "raw-2"],
            ),
            expected_response_type=ReflectResponse,
            summary="Reflection using structured focus payload.",
        ),
        CapabilityAdapterScenario(
            scenario_id=f"{prefix}_fail_closed",
            capability=CapabilityName.REFLECT,
            provider_family=provider,
            request=ReflectRequest(
                request_id=f"{prefix}_fail_closed",
                focus="write a precise postmortem reflection",
                evidence_text="service degraded under concurrent writes",
                fallback_policy=CapabilityFallbackPolicy.FAIL_CLOSED,
            ),
            expected_response_type=ReflectResponse,
            summary="Reflection request that forbids fallback.",
        ),
    )


def _answer_cases(
    provider: CapabilityProviderFamily,
) -> tuple[CapabilityAdapterScenario, ...]:
    prefix = f"{provider.value}_answer"
    return (
        CapabilityAdapterScenario(
            scenario_id=f"{prefix}_basic",
            capability=CapabilityName.ANSWER,
            provider_family=provider,
            request=AnswerRequest(
                request_id=f"{prefix}_basic",
                question="What happened in the latest incident?",
                context_text="incident summary: deployment timed out after 30 seconds",
            ),
            expected_response_type=AnswerResponse,
            summary="Basic question answering over prepared context.",
        ),
        CapabilityAdapterScenario(
            scenario_id=f"{prefix}_constrained",
            capability=CapabilityName.ANSWER,
            provider_family=provider,
            request=AnswerRequest(
                request_id=f"{prefix}_constrained",
                question="Reply with only success or failure.",
                context_text="task result was success after retry",
                support_ids=["episode-007", "episode-007-summary"],
                hard_constraints=["must answer with only success or failure"],
                max_answer_tokens=4,
            ),
            expected_response_type=AnswerResponse,
            summary="Answer path with support ids and hard constraints.",
        ),
        CapabilityAdapterScenario(
            scenario_id=f"{prefix}_fail_closed",
            capability=CapabilityName.ANSWER,
            provider_family=provider,
            request=AnswerRequest(
                request_id=f"{prefix}_fail_closed",
                question="Explain the root cause in one sentence.",
                context_text="two retries failed because credentials had expired",
                fallback_policy=CapabilityFallbackPolicy.FAIL_CLOSED,
            ),
            expected_response_type=AnswerResponse,
            summary="Answer request that requires the primary provider path.",
        ),
    )


def _offline_reconstruct_cases(
    provider: CapabilityProviderFamily,
) -> tuple[CapabilityAdapterScenario, ...]:
    prefix = f"{provider.value}_offline_reconstruct"
    return (
        CapabilityAdapterScenario(
            scenario_id=f"{prefix}_basic",
            capability=CapabilityName.OFFLINE_RECONSTRUCT,
            provider_family=provider,
            request=OfflineReconstructRequest(
                request_id=f"{prefix}_basic",
                objective="reconstruct the cross-episode pattern",
                evidence_text="episode 3 and episode 8 share the same cache invalidation bug",
                episode_ids=["episode-003", "episode-008"],
            ),
            expected_response_type=OfflineReconstructResponse,
            summary="Basic offline reconstruction over two episodes.",
        ),
        CapabilityAdapterScenario(
            scenario_id=f"{prefix}_refs",
            capability=CapabilityName.OFFLINE_RECONSTRUCT,
            provider_family=provider,
            request=OfflineReconstructRequest(
                request_id=f"{prefix}_refs",
                objective="prepare a reusable reconstruction note",
                evidence_text="three incidents show repeated stale-index symptoms",
                episode_ids=["episode-002", "episode-005", "episode-011"],
                evidence_refs=["summary-2", "summary-5", "reflection-11"],
            ),
            expected_response_type=OfflineReconstructResponse,
            summary="Offline reconstruction with explicit evidence refs.",
        ),
        CapabilityAdapterScenario(
            scenario_id=f"{prefix}_fail_closed",
            capability=CapabilityName.OFFLINE_RECONSTRUCT,
            provider_family=provider,
            request=OfflineReconstructRequest(
                request_id=f"{prefix}_fail_closed",
                objective="produce a provider-grade reconstruction only",
                evidence_text="the same outage signature recurred across maintenance windows",
                episode_ids=["episode-004", "episode-006"],
                fallback_policy=CapabilityFallbackPolicy.FAIL_CLOSED,
            ),
            expected_response_type=OfflineReconstructResponse,
            summary="Offline reconstruction request that forbids fallback.",
        ),
    )
