"""Configuration models and resolvers for the Phase K capability layer."""

from __future__ import annotations

from collections.abc import Mapping
from os import environ
from typing import Any

from pydantic import Field

from .contracts import CapabilityModel, CapabilityProviderFamily


class CapabilityAuthMode(str):
    """String constants for provider auth transport."""

    NONE = "none"
    BEARER_TOKEN = "bearer_token"
    API_KEY = "api_key"


class CapabilityAuthConfig(CapabilityModel):
    """Resolved provider auth config. Secrets must stay redacted in outputs."""

    mode: str = Field(default=CapabilityAuthMode.NONE, min_length=1)
    secret_env: str | None = None
    secret_value: str | None = Field(default=None, repr=False)
    parameter_name: str | None = None

    def is_configured(self) -> bool:
        return bool(self.secret_value) or self.mode == CapabilityAuthMode.NONE

    def redacted_summary(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "secret_env": self.secret_env,
            "configured": self.is_configured(),
            "parameter_name": self.parameter_name,
        }


class CapabilityProviderConfig(CapabilityModel):
    """Resolved provider/model/endpoint/auth configuration."""

    provider: str = Field(min_length=1)
    provider_family: CapabilityProviderFamily
    model: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    api_version: str | None = None
    timeout_ms: int = Field(default=30_000, ge=100)
    retry_policy: str = Field(default="default", min_length=1)
    auth: CapabilityAuthConfig = Field(default_factory=CapabilityAuthConfig)

    def redacted_summary(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "provider_family": self.provider_family.value,
            "model": self.model,
            "endpoint": self.endpoint,
            "api_version": self.api_version,
            "timeout_ms": self.timeout_ms,
            "retry_policy": self.retry_policy,
            "auth": self.auth.redacted_summary(),
        }


def resolve_capability_provider_config(
    *,
    selection: Any = None,
    env: Mapping[str, str] | None = None,
    config_file: Mapping[str, Any] | None = None,
) -> CapabilityProviderConfig:
    """Resolve capability provider config from context overrides and environment.

    Priority chain (first non-empty wins):
    ``CLI selection  >  mind.toml [provider]  >  env vars  >  code defaults``
    """

    active_env = env or environ

    # Lazy-load mind.toml [provider] section when caller does not inject one.
    if config_file is None:
        from mind.capabilities.config_file import get_provider_config, load_mind_toml

        config_file = get_provider_config(load_mind_toml())

    # Priority: CLI > env > mind.toml > code defaults
    provider = _first_non_empty(
        _selection_value(selection, "provider"),
        active_env.get("MIND_PROVIDER"),
        config_file.get("provider"),
        "stub",
    )
    family = _provider_family(provider)
    model = _first_non_empty(
        _selection_value(selection, "model"),
        active_env.get("MIND_MODEL"),
        config_file.get("model"),
        _default_model_for_family(family),
    )
    endpoint = _first_non_empty(
        _selection_value(selection, "endpoint"),
        active_env.get("MIND_PROVIDER_ENDPOINT"),
        config_file.get("endpoint"),
        _default_endpoint_for_family(family),
    )
    timeout_ms = _int_or_default(
        _selection_value(selection, "timeout_ms"),
        active_env.get("MIND_PROVIDER_TIMEOUT_MS"),
        config_file.get("timeout_ms"),
        30_000,
    )
    retry_policy = _first_non_empty(
        _selection_value(selection, "retry_policy"),
        active_env.get("MIND_PROVIDER_RETRY_POLICY"),
        config_file.get("retry_policy"),
        "default",
    )
    api_version = _first_non_empty(
        active_env.get("MIND_PROVIDER_API_VERSION"),
        config_file.get("api_version"),
        _default_api_version_for_family(family),
    )

    config_file_secret = config_file.get("api_key") or None
    auth = _resolve_auth_config(
        family=family, env=active_env, config_file_secret=config_file_secret,
    )
    return CapabilityProviderConfig(
        provider=provider,
        provider_family=family,
        model=model,
        endpoint=endpoint,
        api_version=api_version,
        timeout_ms=timeout_ms,
        retry_policy=retry_policy,
        auth=auth,
    )


def _resolve_auth_config(
    *,
    family: CapabilityProviderFamily,
    env: Mapping[str, str],
    config_file_secret: str | None = None,
) -> CapabilityAuthConfig:
    if family is CapabilityProviderFamily.DETERMINISTIC:
        return CapabilityAuthConfig(mode=CapabilityAuthMode.NONE)

    generic_secret = env.get("MIND_PROVIDER_API_KEY")

    # Priority: MIND_PROVIDER_API_KEY env > per-family env > mind.toml api_key
    def _pick_secret(family_env_var: str) -> tuple[str, str | None]:
        if generic_secret:
            return "MIND_PROVIDER_API_KEY", generic_secret
        family_value = env.get(family_env_var)
        if family_value:
            return family_env_var, family_value
        if config_file_secret:
            return "mind.toml", config_file_secret
        return family_env_var, None

    if family is CapabilityProviderFamily.OPENAI:
        secret_env, secret_value = _pick_secret("OPENAI_API_KEY")
        return CapabilityAuthConfig(
            mode=CapabilityAuthMode.BEARER_TOKEN,
            secret_env=secret_env,
            secret_value=secret_value,
            parameter_name="Authorization",
        )
    if family is CapabilityProviderFamily.CLAUDE:
        secret_env, secret_value = _pick_secret("ANTHROPIC_API_KEY")
        return CapabilityAuthConfig(
            mode=CapabilityAuthMode.API_KEY,
            secret_env=secret_env,
            secret_value=secret_value,
            parameter_name="x-api-key",
        )
    if family is CapabilityProviderFamily.GEMINI:
        secret_env, secret_value = _pick_secret("GOOGLE_API_KEY")
        return CapabilityAuthConfig(
            mode=CapabilityAuthMode.API_KEY,
            secret_env=secret_env,
            secret_value=secret_value,
            parameter_name="key",
        )
    raise RuntimeError(f"unsupported provider family {family.value}")


def _provider_family(provider: str) -> CapabilityProviderFamily:
    normalized = provider.strip().lower()
    aliases = {
        "stub": CapabilityProviderFamily.DETERMINISTIC,
        "deterministic": CapabilityProviderFamily.DETERMINISTIC,
        "openai": CapabilityProviderFamily.OPENAI,
        "claude": CapabilityProviderFamily.CLAUDE,
        "anthropic": CapabilityProviderFamily.CLAUDE,
        "gemini": CapabilityProviderFamily.GEMINI,
        "google": CapabilityProviderFamily.GEMINI,
    }
    if normalized not in aliases:
        raise RuntimeError(f"unsupported provider '{provider}'")
    return aliases[normalized]


def _default_model_for_family(family: CapabilityProviderFamily) -> str:
    if family is CapabilityProviderFamily.DETERMINISTIC:
        return "deterministic"
    if family is CapabilityProviderFamily.OPENAI:
        return "gpt-4.1-mini"
    if family is CapabilityProviderFamily.CLAUDE:
        return "claude-3-7-sonnet"
    return "gemini-2.0-flash"


def _default_endpoint_for_family(family: CapabilityProviderFamily) -> str:
    if family is CapabilityProviderFamily.DETERMINISTIC:
        return "local://deterministic"
    if family is CapabilityProviderFamily.OPENAI:
        return "https://api.openai.com/v1/responses"
    if family is CapabilityProviderFamily.CLAUDE:
        return "https://api.anthropic.com/v1/messages"
    return "https://generativelanguage.googleapis.com/v1beta/models"


def _default_api_version_for_family(family: CapabilityProviderFamily) -> str | None:
    if family is CapabilityProviderFamily.DETERMINISTIC:
        return "deterministic-v1"
    if family is CapabilityProviderFamily.OPENAI:
        return "v1"
    if family is CapabilityProviderFamily.CLAUDE:
        return "2023-06-01"
    return "v1beta"


def _selection_value(selection: Any, field: str) -> Any:
    if selection is None:
        return None
    if isinstance(selection, Mapping):
        return selection.get(field)
    return getattr(selection, field, None)


def _int_or_default(*values: Any) -> int:
    fallback = 30_000
    for value in values:
        if value in (None, ""):
            continue
        return int(value)
    return fallback


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None
