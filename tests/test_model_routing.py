"""Tests for Phase γ-3: Hierarchical model routing."""

from __future__ import annotations

from mind.capabilities.config import CapabilityProviderConfig, CapabilityProviderFamily
from mind.capabilities.contracts import (
    CapabilityName,
    CapabilityRoutingConfig,
    SummarizeResponse,
)
from mind.capabilities.service import CapabilityService


def _deterministic_config() -> CapabilityProviderConfig:
    return CapabilityProviderConfig(
        provider="stub",
        provider_family=CapabilityProviderFamily.DETERMINISTIC,
        model="deterministic",
        endpoint="local://deterministic",
    )


# ─── CapabilityRoutingConfig ──────────────────────────────────────────────────


class TestCapabilityRoutingConfig:
    def test_empty_routing_config(self) -> None:
        config = CapabilityRoutingConfig()
        assert config.routes == {}

    def test_routing_with_single_capability(self) -> None:
        det = _deterministic_config()
        config = CapabilityRoutingConfig(routes={CapabilityName.SUMMARIZE: det})
        assert CapabilityName.SUMMARIZE in config.routes

    def test_routing_with_multiple_capabilities(self) -> None:
        det = _deterministic_config()
        config = CapabilityRoutingConfig(
            routes={
                CapabilityName.SUMMARIZE: det,
                CapabilityName.ANSWER: det,
            }
        )
        assert len(config.routes) == 2


# ─── CapabilityService routing ────────────────────────────────────────────────


class TestCapabilityServiceRouting:
    def test_service_accepts_routing_config(self) -> None:
        det = _deterministic_config()
        routing = CapabilityRoutingConfig(routes={CapabilityName.SUMMARIZE: det})
        service = CapabilityService(routing_config=routing)
        assert service._routing_config is routing

    def test_service_without_routing_config(self) -> None:
        service = CapabilityService()
        assert service._routing_config is None

    def test_summarize_with_routing_uses_routed_provider(self) -> None:
        """When a SUMMARIZE route is configured, it should be used for summarize calls."""
        from mind.capabilities.contracts import SummarizeRequest

        det = _deterministic_config()
        routing = CapabilityRoutingConfig(routes={CapabilityName.SUMMARIZE: det})
        service = CapabilityService(routing_config=routing)
        req = SummarizeRequest(
            request_id="test-route-1",
            source_text="hello world this is a test sentence",
        )
        response = service.invoke(req)
        assert response.capability == CapabilityName.SUMMARIZE
        assert response.summary_text

    def test_answer_without_routing_falls_back_to_default(self) -> None:
        from mind.capabilities.contracts import AnswerRequest

        service = CapabilityService()
        req = AnswerRequest(
            request_id="test-route-2",
            question="what is this?",
            context_text="this is a test context string",
        )
        response = service.invoke(req)
        assert response.capability == CapabilityName.ANSWER
        assert response.answer_text

    def test_routing_only_applies_to_matched_capability(self) -> None:
        """SUMMARIZE routing does not affect REFLECT calls."""
        from mind.capabilities.contracts import ReflectRequest, SummarizeRequest

        det = _deterministic_config()
        routing = CapabilityRoutingConfig(routes={CapabilityName.SUMMARIZE: det})
        service = CapabilityService(routing_config=routing)

        # SUMMARIZE — routed
        sum_req = SummarizeRequest(
            request_id="test-route-3a",
            source_text="test content for summarise",
        )
        sum_response = service.invoke(sum_req)
        assert sum_response.capability == CapabilityName.SUMMARIZE

        # REFLECT — uses default (no routing override for REFLECT)
        ref_req = ReflectRequest(
            request_id="test-route-3b",
            focus="episode review",
            evidence_text="evidence for reflection",
        )
        ref_response = service.invoke(ref_req)
        assert ref_response.capability == CapabilityName.REFLECT

    def test_backward_compat_no_routing_config(self) -> None:
        """Service without routing_config behaves identically to pre-γ behaviour."""
        from mind.capabilities.contracts import SummarizeRequest

        service = CapabilityService()
        req = SummarizeRequest(
            request_id="test-compat-1",
            source_text="backward compatibility test sentence",
        )
        response = service.invoke(req)
        assert isinstance(response, SummarizeResponse)
        assert response.summary_text


# ─── CLI model_routing config ─────────────────────────────────────────────────


class TestCliModelRoutingConfig:
    def test_resolve_cli_config_model_routing_param(self) -> None:
        from mind.cli_config import resolve_cli_config

        config = resolve_cli_config(
            allow_sqlite=True,
            model_routing={"summarize": "gpt-4.1-mini", "answer": "gpt-4.1"},
        )
        assert config.model_routing == {"summarize": "gpt-4.1-mini", "answer": "gpt-4.1"}

    def test_resolve_cli_config_no_routing_by_default(self) -> None:
        from mind.cli_config import resolve_cli_config

        config = resolve_cli_config(allow_sqlite=True)
        assert config.model_routing is None

    def test_model_routing_from_env(self) -> None:
        import json

        from mind.cli_config import resolve_cli_config

        routing = {"summarize": "small-model", "reflect": "large-model"}
        config = resolve_cli_config(
            allow_sqlite=True,
            env={
                "MIND_ALLOW_SQLITE_FOR_TESTS": "1",
                "MIND_MODEL_ROUTING": json.dumps(routing),
            },
        )
        assert config.model_routing == routing

    def test_model_routing_from_env_invalid_json_ignored(self) -> None:
        from mind.cli_config import resolve_cli_config

        config = resolve_cli_config(
            allow_sqlite=True,
            env={
                "MIND_ALLOW_SQLITE_FOR_TESTS": "1",
                "MIND_MODEL_ROUTING": "not-valid-json",
            },
        )
        # Invalid JSON should not raise; routing should be None.
        assert config.model_routing is None
