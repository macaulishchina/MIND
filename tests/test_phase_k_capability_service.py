from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from mind.capabilities import (
    AnswerRequest,
    CapabilityAuthConfig,
    CapabilityFallbackPolicy,
    CapabilityInvocationTrace,
    CapabilityName,
    CapabilityProviderConfig,
    CapabilityProviderFamily,
    CapabilityService,
    CapabilityServiceError,
    OfflineReconstructRequest,
    OfflineReconstructResponse,
    ReflectRequest,
    ReflectResponse,
    SummarizeRequest,
    SummarizeResponse,
    build_capability_adapters_from_environment,
)
from mind.fixtures.golden_episode_set import build_core_object_showcase, build_golden_episode_set
from mind.kernel.store import SQLiteMemoryStore
from mind.offline import (
    OfflineJobKind,
    OfflineMaintenanceService,
    PromoteSchemaJobPayload,
    new_offline_job,
)
from mind.primitives.contracts import PrimitiveOutcome
from mind.primitives.service import PrimitiveService


def _fixed_clock() -> datetime:
    return datetime(2026, 3, 11, 13, 0, tzinfo=UTC)


def test_capability_service_handles_all_four_capabilities_deterministically() -> None:
    service = CapabilityService(clock=_fixed_clock)

    summarize = service.summarize(
        SummarizeRequest(request_id="sum-1", source_text="alpha beta gamma delta epsilon")
    )
    reflect = service.reflect(
        ReflectRequest(
            request_id="ref-1",
            focus="postmortem",
            evidence_text="deploy failed after timeout and stale token usage",
        )
    )
    answer = service.answer(
        AnswerRequest(
            request_id="ans-1",
            question="What happened?",
            context_text="deployment succeeded after the second retry",
        )
    )
    reconstruct = service.offline_reconstruct(
        OfflineReconstructRequest(
            request_id="off-1",
            objective="reconstruct pattern",
            evidence_text="two incidents share the same invalid cache bust sequence",
            episode_ids=["episode-001", "episode-007"],
        )
    )

    assert summarize.summary_text.startswith("alpha beta")
    assert reflect.reflection_text.startswith("postmortem:")
    assert answer.answer_text.startswith("deployment succeeded")
    assert reconstruct.supporting_episode_ids == ["episode-001", "episode-007"]
    assert summarize.trace.provider_family is CapabilityProviderFamily.DETERMINISTIC
    assert reconstruct.trace.endpoint == "local://deterministic"


def test_capability_service_honors_success_failure_constraint() -> None:
    service = CapabilityService(clock=_fixed_clock)

    answer = service.answer(
        AnswerRequest(
            request_id="ans-constraint",
            question="Reply with only success or failure.",
            context_text="final result was success after retry",
            hard_constraints=["must answer with only success or failure"],
        )
    )

    assert answer.answer_text == "success"


def test_capability_service_falls_back_to_deterministic_when_primary_missing() -> None:
    service = CapabilityService(
        provider_config=CapabilityProviderConfig(
            provider="openai",
            provider_family=CapabilityProviderFamily.OPENAI,
            model="gpt-4.1",
            endpoint="https://api.openai.com/v1/responses",
            api_version="v1",
            timeout_ms=30_000,
            retry_policy="default",
            auth=CapabilityAuthConfig(
                mode="bearer_token",
                secret_env="OPENAI_API_KEY",
                secret_value=None,
                parameter_name="Authorization",
            ),
        ),
        clock=_fixed_clock,
    )

    response = service.summarize(
        SummarizeRequest(request_id="sum-fallback", source_text="fallback source text")
    )

    assert response.trace.provider_family is CapabilityProviderFamily.DETERMINISTIC
    assert response.trace.fallback_used is True
    assert "openai" in str(response.trace.fallback_reason)


def test_capability_service_fail_closed_rejects_missing_primary_adapter() -> None:
    service = CapabilityService(
        provider_config=CapabilityProviderConfig(
            provider="claude",
            provider_family=CapabilityProviderFamily.CLAUDE,
            model="claude-3-7-sonnet",
            endpoint="https://api.anthropic.com/v1/messages",
            api_version="2023-06-01",
            timeout_ms=30_000,
            retry_policy="default",
            auth=CapabilityAuthConfig(
                mode="api_key",
                secret_env="ANTHROPIC_API_KEY",
                secret_value=None,
                parameter_name="x-api-key",
            ),
        ),
        clock=_fixed_clock,
    )

    with pytest.raises(CapabilityServiceError, match="primary capability adapter unavailable"):
        service.reflect(
            ReflectRequest(
                request_id="ref-fail-closed",
                focus="reflection",
                evidence_text="some evidence",
                fallback_policy=CapabilityFallbackPolicy.FAIL_CLOSED,
            )
        )


def test_capability_service_request_scoped_provider_override_beats_base_provider() -> None:
    service = CapabilityService(
        provider_config=CapabilityProviderConfig(
            provider="openai",
            provider_family=CapabilityProviderFamily.OPENAI,
            model="gpt-4.1",
            endpoint="https://api.openai.com/v1/responses",
            api_version="v1",
            timeout_ms=30_000,
            retry_policy="default",
            auth=CapabilityAuthConfig(
                mode="bearer_token",
                secret_env="OPENAI_API_KEY",
                secret_value=None,
                parameter_name="Authorization",
            ),
        ),
        clock=_fixed_clock,
    )

    response = service.summarize(
        SummarizeRequest(request_id="sum-request-override", source_text="override source text"),
        provider_config=CapabilityProviderConfig(
            provider="stub",
            provider_family=CapabilityProviderFamily.DETERMINISTIC,
            model="deterministic",
            endpoint="local://deterministic",
            api_version="deterministic-v1",
            timeout_ms=12_000,
            retry_policy="none",
            auth=CapabilityAuthConfig(mode="none"),
        ),
    )

    assert response.trace.provider_family is CapabilityProviderFamily.DETERMINISTIC
    assert response.trace.fallback_used is False
    assert response.trace.endpoint == "local://deterministic"


def test_build_capability_adapters_from_environment_returns_only_configured_providers() -> None:
    adapters = build_capability_adapters_from_environment(
        provider_families=(
            CapabilityProviderFamily.OPENAI,
            CapabilityProviderFamily.CLAUDE,
            CapabilityProviderFamily.GEMINI,
        ),
        env={
            "OPENAI_API_KEY": "openai-secret",
            "GOOGLE_API_KEY": "google-secret",
        },
        clock=_fixed_clock,
    )

    assert [adapter.descriptor.provider_family for adapter in adapters] == [
        CapabilityProviderFamily.OPENAI,
        CapabilityProviderFamily.GEMINI,
    ]


def test_primitive_summarize_delegates_to_capability_service(tmp_path: Path) -> None:
    captured: dict[str, SummarizeRequest] = {}

    class _FakeCapabilityService:
        def summarize(
            self,
            request: SummarizeRequest,
            *,
            provider_config: CapabilityProviderConfig | None = None,
        ) -> SummarizeResponse:
            captured["request"] = request
            return SummarizeResponse(
                summary_text="capability summary output",
                source_refs=list(request.source_refs),
                trace=_trace(),
            )

    showcase = build_core_object_showcase()
    with SQLiteMemoryStore(tmp_path / "phase_k_summarize.sqlite3") as store:
        store.insert_objects(showcase)
        service = PrimitiveService(
            store,
            clock=_fixed_clock,
            capability_service=_FakeCapabilityService(),  # type: ignore[arg-type]
        )

        result = service.summarize(
            {
                "input_refs": [showcase[0]["id"]],
                "summary_scope": "episode",
                "target_kind": "summary_note",
            },
            _primitive_context(),
        )

        assert result.outcome is PrimitiveOutcome.SUCCESS
        assert captured["request"].capability is CapabilityName.SUMMARIZE
        assert captured["request"].source_refs == [showcase[0]["id"]]
        assert result.response is not None
        stored = store.read_object(result.response["summary_object_id"])
        assert stored is not None
        assert stored["content"]["summary"] == "capability summary output"


def test_primitive_summarize_passes_provider_selection_to_capability_service(
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    class _FakeCapabilityService:
        def summarize(
            self,
            request: SummarizeRequest,
            *,
            provider_config: CapabilityProviderConfig | None = None,
        ) -> SummarizeResponse:
            captured["request"] = request
            captured["provider_config"] = provider_config
            return SummarizeResponse(
                summary_text="provider-selected summary",
                source_refs=list(request.source_refs),
                trace=_trace(),
            )

    showcase = build_core_object_showcase()
    with SQLiteMemoryStore(tmp_path / "phase_k_summarize_provider_selection.sqlite3") as store:
        store.insert_objects(showcase)
        service = PrimitiveService(
            store,
            clock=_fixed_clock,
            capability_service=_FakeCapabilityService(),  # type: ignore[arg-type]
        )

        result = service.summarize(
            {
                "input_refs": [showcase[0]["id"]],
                "summary_scope": "episode",
                "target_kind": "summary_note",
            },
            _primitive_context(
                provider_selection={
                    "provider": "openai",
                    "model": "gpt-4.1-mini",
                    "endpoint": "https://api.openai.com/v1/responses",
                    "timeout_ms": 12_000,
                    "retry_policy": "none",
                }
            ),
        )

        assert result.outcome is PrimitiveOutcome.SUCCESS
        assert captured["provider_config"] is not None
        assert captured["provider_config"].provider_family is CapabilityProviderFamily.OPENAI
        assert captured["provider_config"].model == "gpt-4.1-mini"


def test_primitive_summarize_rejects_invalid_provider_selection(tmp_path: Path) -> None:
    showcase = build_core_object_showcase()
    with SQLiteMemoryStore(tmp_path / "phase_k_summarize_invalid_provider.sqlite3") as store:
        store.insert_objects(showcase)
        service = PrimitiveService(store, clock=_fixed_clock)

        result = service.summarize(
            {
                "input_refs": [showcase[0]["id"]],
                "summary_scope": "episode",
                "target_kind": "summary_note",
            },
            _primitive_context(
                provider_selection={
                    "provider": "unknown-provider",
                    "model": "mystery-model",
                }
            ),
        )

        assert result.outcome is PrimitiveOutcome.REJECTED
        assert result.error is not None
        assert result.error.code.value == "unsupported_operation"


def test_primitive_reflect_delegates_to_capability_service(tmp_path: Path) -> None:
    captured: dict[str, ReflectRequest] = {}
    episode = next(
        fixture for fixture in build_golden_episode_set() if fixture.episode_id == "episode-004"
    )

    class _FakeCapabilityService:
        def reflect(
            self,
            request: ReflectRequest,
            *,
            provider_config: CapabilityProviderConfig | None = None,
        ) -> ReflectResponse:
            captured["request"] = request
            return ReflectResponse(
                reflection_text="Episode failed; reflection focus: delegated",
                claims=["failure", "delegated"],
                evidence_refs=list(request.evidence_refs),
                trace=_trace(),
            )

    with SQLiteMemoryStore(tmp_path / "phase_k_reflect.sqlite3") as store:
        store.insert_objects(episode.objects)
        service = PrimitiveService(
            store,
            clock=_fixed_clock,
            capability_service=_FakeCapabilityService(),  # type: ignore[arg-type]
        )

        result = service.reflect(
            {
                "episode_id": episode.episode_id,
                "focus": "failure analysis",
            },
            _primitive_context(),
        )

        assert result.outcome is PrimitiveOutcome.SUCCESS
        assert captured["request"].capability is CapabilityName.REFLECT
        assert captured["request"].episode_id == episode.episode_id
        assert captured["request"].outcome_hint == "failure"
        assert result.response is not None
        stored = store.read_object(result.response["reflection_object_id"])
        assert stored is not None
        assert stored["content"]["summary"] == "Episode failed; reflection focus: delegated"


def test_primitive_reflect_passes_provider_selection_to_capability_service(
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}
    episode = next(
        fixture for fixture in build_golden_episode_set() if fixture.episode_id == "episode-004"
    )

    class _FakeCapabilityService:
        def reflect(
            self,
            request: ReflectRequest,
            *,
            provider_config: CapabilityProviderConfig | None = None,
        ) -> ReflectResponse:
            captured["request"] = request
            captured["provider_config"] = provider_config
            return ReflectResponse(
                reflection_text="provider-selected reflection",
                claims=["delegated"],
                evidence_refs=list(request.evidence_refs),
                trace=_trace(),
            )

    with SQLiteMemoryStore(tmp_path / "phase_k_reflect_provider_selection.sqlite3") as store:
        store.insert_objects(episode.objects)
        service = PrimitiveService(
            store,
            clock=_fixed_clock,
            capability_service=_FakeCapabilityService(),  # type: ignore[arg-type]
        )

        result = service.reflect(
            {
                "episode_id": episode.episode_id,
                "focus": "failure analysis",
            },
            _primitive_context(
                provider_selection={
                    "provider": "gemini",
                    "model": "gemini-2.0-flash",
                    "endpoint": "https://generativelanguage.googleapis.com/v1beta/models",
                    "timeout_ms": 9_000,
                    "retry_policy": "aggressive",
                }
            ),
        )

        assert result.outcome is PrimitiveOutcome.SUCCESS
        assert captured["provider_config"] is not None
        assert captured["provider_config"].provider_family is CapabilityProviderFamily.GEMINI
        assert captured["provider_config"].model == "gemini-2.0-flash"


def test_offline_promotion_delegates_to_offline_reconstruct_capability(tmp_path: Path) -> None:
    captured: dict[str, OfflineReconstructRequest] = {}
    episodes = build_golden_episode_set()
    reflect_episode = next(fixture for fixture in episodes if fixture.episode_id == "episode-004")
    promotion_episode = next(fixture for fixture in episodes if fixture.episode_id == "episode-008")

    class _FakeCapabilityService:
        def offline_reconstruct(
            self,
            request: OfflineReconstructRequest,
            *,
            provider_config: CapabilityProviderConfig | None = None,
        ) -> OfflineReconstructResponse:
            captured["request"] = request
            return OfflineReconstructResponse(
                reconstruction_text="delegated reconstruction rule",
                supporting_episode_ids=list(request.episode_ids),
                evidence_refs=list(request.evidence_refs),
                trace=_trace(),
            )

    with SQLiteMemoryStore(tmp_path / "phase_k_offline_reconstruct.sqlite3") as store:
        store.insert_objects(reflect_episode.objects)
        store.insert_objects(promotion_episode.objects)
        service = OfflineMaintenanceService(
            store,
            clock=_fixed_clock,
            capability_service=_FakeCapabilityService(),  # type: ignore[arg-type]
        )

        result = service.process_job(
            new_offline_job(
                job_id="phase-k-promote",
                job_kind=OfflineJobKind.PROMOTE_SCHEMA,
                payload=PromoteSchemaJobPayload(
                    target_refs=[
                        f"{reflect_episode.episode_id}-reflection",
                        f"{promotion_episode.episode_id}-reflection",
                    ],
                    reason="promote repeated stale-memory pattern",
                ),
                now=_fixed_clock(),
            ),
            actor="phase-k-offline",
        )

        assert captured["request"].capability is CapabilityName.OFFLINE_RECONSTRUCT
        assert captured["request"].episode_ids == [
            reflect_episode.episode_id,
            promotion_episode.episode_id,
        ]
        assert captured["request"].evidence_refs == [
            f"{reflect_episode.episode_id}-reflection",
            f"{promotion_episode.episode_id}-reflection",
        ]
        assert "cross-episode support" in captured["request"].objective
        assert result["reconstruction_text"] == "delegated reconstruction rule"
        schema = store.read_object(str(result["schema_object_id"]))
        assert schema["content"]["rule"] == "delegated reconstruction rule"


def test_offline_promotion_passes_provider_selection_to_capability_service(
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}
    episodes = build_golden_episode_set()
    reflect_episode = next(fixture for fixture in episodes if fixture.episode_id == "episode-004")
    promotion_episode = next(fixture for fixture in episodes if fixture.episode_id == "episode-008")

    class _FakeCapabilityService:
        def offline_reconstruct(
            self,
            request: OfflineReconstructRequest,
            *,
            provider_config: CapabilityProviderConfig | None = None,
        ) -> OfflineReconstructResponse:
            captured["request"] = request
            captured["provider_config"] = provider_config
            return OfflineReconstructResponse(
                reconstruction_text="provider-selected reconstruction",
                supporting_episode_ids=list(request.episode_ids),
                evidence_refs=list(request.evidence_refs),
                trace=_trace(),
            )

    with SQLiteMemoryStore(
        tmp_path / "phase_k_offline_reconstruct_provider_selection.sqlite3"
    ) as store:
        store.insert_objects(reflect_episode.objects)
        store.insert_objects(promotion_episode.objects)
        service = OfflineMaintenanceService(
            store,
            clock=_fixed_clock,
            capability_service=_FakeCapabilityService(),  # type: ignore[arg-type]
        )

        result = service.process_job(
            new_offline_job(
                job_id="phase-k-promote-provider-selection",
                job_kind=OfflineJobKind.PROMOTE_SCHEMA,
                payload=PromoteSchemaJobPayload(
                    target_refs=[
                        f"{reflect_episode.episode_id}-reflection",
                        f"{promotion_episode.episode_id}-reflection",
                    ],
                    reason="promote repeated stale-memory pattern",
                ),
                now=_fixed_clock(),
            ),
            actor="phase-k-offline",
            provider_selection={
                "provider": "claude",
                "model": "claude-3-7-sonnet",
                "endpoint": "https://api.anthropic.com/v1/messages",
                "timeout_ms": 8_000,
                "retry_policy": "none",
            },
        )

        assert captured["provider_config"] is not None
        assert captured["provider_config"].provider_family is CapabilityProviderFamily.CLAUDE
        assert captured["provider_config"].model == "claude-3-7-sonnet"
        assert result["reconstruction_text"] == "provider-selected reconstruction"


def _trace() -> CapabilityInvocationTrace:
    return CapabilityInvocationTrace(
        provider_family=CapabilityProviderFamily.DETERMINISTIC,
        model="deterministic",
        endpoint="local://deterministic",
        version="deterministic-v1",
        started_at=_fixed_clock(),
        completed_at=_fixed_clock(),
        duration_ms=0,
    )


def _primitive_context(
    *,
    provider_selection: dict[str, object] | None = None,
) -> dict[str, object]:
    context: dict[str, object] = {
        "actor": "phase-k-service",
        "budget_scope_id": "phase-k",
        "budget_limit": 100.0,
        "capabilities": ["memory_read"],
    }
    if provider_selection is not None:
        context["provider_selection"] = provider_selection
    return context
