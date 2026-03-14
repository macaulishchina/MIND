from __future__ import annotations

import pytest

from mind.app.context import ProviderSelection
from mind.capabilities import (
    CapabilityAuthMode,
    CapabilityProviderFamily,
    resolve_capability_provider_config,
)


def test_default_capability_provider_config_is_deterministic() -> None:
    resolved = resolve_capability_provider_config(env={})

    assert resolved.provider == "stub"
    assert resolved.provider_family is CapabilityProviderFamily.DETERMINISTIC
    assert resolved.model == "deterministic"
    assert resolved.endpoint == "local://deterministic"
    assert resolved.api_version == "deterministic-v1"
    assert resolved.auth.mode == CapabilityAuthMode.NONE
    assert resolved.auth.is_configured() is True


def test_openai_provider_uses_specific_api_key_and_defaults() -> None:
    resolved = resolve_capability_provider_config(
        env={
            "MIND_PROVIDER": "openai",
            "OPENAI_API_KEY": "secret-openai-key",
        }
    )

    assert resolved.provider == "openai"
    assert resolved.provider_family is CapabilityProviderFamily.OPENAI
    assert resolved.model == "gpt-4.1-mini"
    assert resolved.endpoint == "https://api.openai.com/v1/responses"
    assert resolved.auth.mode == CapabilityAuthMode.BEARER_TOKEN
    assert resolved.auth.secret_env == "OPENAI_API_KEY"
    assert resolved.auth.parameter_name == "Authorization"
    assert resolved.auth.is_configured() is True
    assert "secret-openai-key" not in str(resolved.redacted_summary())


def test_provider_selection_override_beats_environment() -> None:
    selection = ProviderSelection(
        provider="claude",
        model="claude-3-7-sonnet-custom",
        endpoint="https://claude.example/v1/messages",
        timeout_ms=12_000,
        retry_policy="none",
    )
    resolved = resolve_capability_provider_config(
        selection=selection,
        env={
            "MIND_PROVIDER": "openai",
            "MIND_MODEL": "gpt-4.1",
            "ANTHROPIC_API_KEY": "anthropic-secret",
        },
    )

    assert resolved.provider == "claude"
    assert resolved.provider_family is CapabilityProviderFamily.CLAUDE
    assert resolved.model == "claude-3-7-sonnet-custom"
    assert resolved.endpoint == "https://claude.example/v1/messages"
    assert resolved.timeout_ms == 12_000
    assert resolved.retry_policy == "none"
    assert resolved.auth.secret_env == "ANTHROPIC_API_KEY"


def test_generic_provider_api_key_override_works_for_gemini() -> None:
    resolved = resolve_capability_provider_config(
        env={
            "MIND_PROVIDER": "gemini",
            "MIND_PROVIDER_API_KEY": "generic-provider-key",
            "MIND_PROVIDER_ENDPOINT": "https://gemini.example/v1/models",
            "MIND_PROVIDER_TIMEOUT_MS": "4500",
            "MIND_PROVIDER_RETRY_POLICY": "aggressive",
        }
    )

    assert resolved.provider_family is CapabilityProviderFamily.GEMINI
    assert resolved.endpoint == "https://gemini.example/v1/models"
    assert resolved.timeout_ms == 4500
    assert resolved.retry_policy == "aggressive"
    assert resolved.auth.secret_env == "MIND_PROVIDER_API_KEY"
    assert resolved.auth.parameter_name == "key"


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="unsupported provider"):
        resolve_capability_provider_config(env={"MIND_PROVIDER": "unknown-provider"})
