"""Provider environment composition for frontend runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mind.app.context import ProviderSelection

_UNSET = object()
_BUILTIN_PROVIDERS = frozenset({"stub", "deterministic"})


def normalize_provider_name(provider: str) -> str:
    return "deterministic" if provider in _BUILTIN_PROVIDERS else provider


def compose_provider_env(
    base_env: dict[str, str],
    current_selection: ProviderSelection,
    state_dev_mode: bool,
    *,
    preferences: Mapping[str, Any] | None = None,
    provider: str | None = None,
    request_input: Mapping[str, Any] | None = None,
    dev_mode: bool | None = None,
) -> dict[str, str]:
    from mind.app.frontend_settings import (
        find_frontend_llm_service,
        frontend_llm_provider_catalog,
        load_frontend_llm_state,
        provider_secret_env,
        resolve_frontend_llm_runtime_endpoint,
    )

    active_env = dict(base_env)
    llm_state = load_frontend_llm_state(preferences)
    llm_catalog = frontend_llm_provider_catalog()
    request_payload = request_input if isinstance(request_input, Mapping) else {}
    selected_service = find_frontend_llm_service(
        llm_state,
        service_id=(
            str(request_payload.get("service_id"))
            if request_payload.get("service_id") is not None
            else None
        ),
        protocol=(
            str(request_payload.get("provider"))
            if request_payload.get("provider") is not None
            else provider
        ),
    )
    requested_provider = (
        str(request_payload.get("provider"))
        if request_payload.get("provider") is not None
        else (
            str(selected_service["protocol"])
            if selected_service is not None
            else provider or current_selection.provider
        )
    )
    next_provider = normalize_provider_name(requested_provider)
    if request_payload.get("model") is not None:
        next_model = str(request_payload.get("model"))
    elif selected_service is not None and selected_service.get("active_model") is not None:
        next_model = str(selected_service["active_model"])
    elif next_provider in llm_catalog:
        next_model = str(llm_catalog[next_provider]["models"][0])
    elif next_provider in _BUILTIN_PROVIDERS:
        next_model = "deterministic"
    else:
        next_model = current_selection.model
    active_env["MIND_PROVIDER"] = next_provider
    active_env["MIND_MODEL"] = next_model

    request_endpoint = request_payload.get("endpoint") if request_payload else _UNSET
    if next_provider == "deterministic":
        active_env.pop("MIND_PROVIDER_ENDPOINT", None)
    elif request_endpoint is _UNSET:
        if selected_service is not None:
            active_env["MIND_PROVIDER_ENDPOINT"] = resolve_frontend_llm_runtime_endpoint(
                next_provider,
                str(selected_service["endpoint"]),
            )
        elif (
            next_provider == current_selection.provider
            and current_selection.endpoint is not None
        ):
            active_env["MIND_PROVIDER_ENDPOINT"] = current_selection.endpoint
        else:
            active_env.pop("MIND_PROVIDER_ENDPOINT", None)
    elif request_endpoint == "":
        active_env.pop("MIND_PROVIDER_ENDPOINT", None)
    elif request_endpoint is not None:
        endpoint_value = str(request_endpoint).strip()
        if endpoint_value:
            active_env["MIND_PROVIDER_ENDPOINT"] = resolve_frontend_llm_runtime_endpoint(
                next_provider,
                endpoint_value,
            )
        else:
            active_env.pop("MIND_PROVIDER_ENDPOINT", None)

    request_api_key = request_payload.get("api_key") if request_payload else _UNSET
    if request_api_key is _UNSET and selected_service is not None:
        api_key_override = selected_service.get("api_key")
    elif isinstance(request_api_key, str) and request_api_key.strip():
        api_key_override = request_api_key.strip()
    else:
        api_key_override = None
    active_env.pop("MIND_PROVIDER_API_KEY", None)
    for secret_env_key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        active_env.pop(secret_env_key, None)
    if (
        next_provider != "deterministic"
        and isinstance(api_key_override, str)
        and api_key_override
    ):
        secret_env = provider_secret_env(next_provider)
        if secret_env is not None:
            active_env[secret_env] = api_key_override

    if next_provider == current_selection.provider:
        active_env["MIND_PROVIDER_TIMEOUT_MS"] = str(current_selection.timeout_ms)
        active_env["MIND_PROVIDER_RETRY_POLICY"] = current_selection.retry_policy
    else:
        active_env.pop("MIND_PROVIDER_TIMEOUT_MS", None)
        active_env.pop("MIND_PROVIDER_RETRY_POLICY", None)
    active_env["MIND_DEV_MODE"] = (
        "true" if (state_dev_mode if dev_mode is None else dev_mode) else "false"
    )
    return active_env
