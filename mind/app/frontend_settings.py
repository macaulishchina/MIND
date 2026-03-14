"""Frontend-facing settings surface contracts (moved to app layer for architecture compliance)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from os import environ
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from pydantic import Field, model_validator

from mind.app.contracts import FrontendModel
from mind.app.services.system import build_config_summary_payload, build_provider_status_payload
from mind.capabilities import CapabilityProviderFamily, resolve_capability_provider_config
from mind.cli_config import CliBackend, CliProfile, ResolvedCliConfig, resolve_cli_config

_LLM_PROVIDER_CATALOG: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "OpenAI 协议",
        "provider_label": "OpenAI",
        "default_name": "OpenAI 官方",
        "default_icon": "OA",
        "models": ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini"],
        "default_endpoint": "https://api.openai.com/v1",
        "secret_env": "OPENAI_API_KEY",
        "auth_mode": "bearer_token",
    },
    "claude": {
        "label": "Claude 协议",
        "provider_label": "Claude",
        "default_name": "Claude 官方",
        "default_icon": "CL",
        "models": ["claude-3-7-sonnet", "claude-3-5-haiku", "claude-3-7-sonnet-custom"],
        "default_endpoint": "https://api.anthropic.com/v1",
        "secret_env": "ANTHROPIC_API_KEY",
        "auth_mode": "api_key",
    },
    "gemini": {
        "label": "Gemini 协议",
        "provider_label": "Gemini",
        "default_name": "Gemini 官方",
        "default_icon": "GM",
        "models": ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro"],
        "default_endpoint": "https://generativelanguage.googleapis.com/v1beta",
        "secret_env": "GOOGLE_API_KEY",
        "auth_mode": "api_key",
    },
}


class FrontendSettingsUpdateRequest(FrontendModel):
    """Frozen frontend-facing config mutation contract."""

    backend: str | None = None
    profile: str | None = None
    service_id: str | None = None
    provider: str | None = None
    model: str | None = None
    endpoint: str | None = None
    api_key: str | None = None
    dev_mode: bool | None = None

    @model_validator(mode="after")
    def enforce_non_empty(self) -> FrontendSettingsUpdateRequest:
        if (
            self.backend is None
            and self.profile is None
            and self.service_id is None
            and self.provider is None
            and self.model is None
            and self.endpoint is None
            and self.api_key is None
            and self.dev_mode is None
        ):
            raise ValueError("frontend settings updates require at least one change")
        return self


class FrontendRuntimeSettingsView(FrontendModel):
    backend: str = Field(min_length=1)
    profile: str = Field(min_length=1)
    backend_source: str = Field(min_length=1)
    profile_source: str = Field(min_length=1)
    scope: str = Field(default="process", min_length=1)
    source: str = Field(default="env", min_length=1)
    dev_mode: bool
    dev_telemetry_configured: bool
    debug_available: bool


class FrontendProviderSettingsView(FrontendModel):
    provider: str = Field(min_length=1)
    provider_family: str = Field(min_length=1)
    model: str = Field(min_length=1)
    endpoint: str | None = None
    source_service_id: str | None = None
    timeout_ms: int = Field(default=30_000, ge=100)
    retry_policy: str = Field(min_length=1)
    status: str = Field(min_length=1)
    execution: str = Field(min_length=1)
    auth_configured: bool
    auth_mode: str = Field(min_length=1)
    auth_secret_env: str | None = None
    auth_parameter_name: str | None = None
    supported_capabilities: list[str] = Field(default_factory=list)


class FrontendSettingsOptionCatalog(FrontendModel):
    backends: list[str] = Field(default_factory=list)
    profiles: list[str] = Field(default_factory=list)
    provider_families: list[str] = Field(default_factory=list)
    editable_keys: list[str] = Field(default_factory=list)


class FrontendLlmProtocolView(FrontendModel):
    protocol: str = Field(min_length=1)
    label: str = Field(min_length=1)
    default_name: str = Field(min_length=1)
    default_icon: str = Field(min_length=1)
    default_endpoint: str = Field(min_length=1)
    auth_mode: str = Field(min_length=1)


class FrontendLlmServiceView(FrontendModel):
    service_id: str = Field(min_length=1)
    protocol: str = Field(min_length=1)
    name: str = Field(min_length=1)
    icon: str | None = None
    endpoint: str = Field(min_length=1)
    uses_official_endpoint: bool = True
    api_key_saved: bool = False
    api_key_masked: str | None = None
    active_model: str | None = None
    model_options: list[str] = Field(default_factory=list)
    models_synced: bool = False
    is_active: bool = False


class FrontendLlmSettingsView(FrontendModel):
    selected_service_id: str | None = None
    active_service_id: str | None = None
    protocols: list[FrontendLlmProtocolView] = Field(default_factory=list)
    services: list[FrontendLlmServiceView] = Field(default_factory=list)


class FrontendLlmServiceUpsertRequest(FrontendModel):
    service_id: str | None = None
    protocol: str = Field(min_length=1)
    name: str | None = None
    icon: str | None = None
    endpoint: str | None = None
    api_key: str | None = None
    model: str | None = None

    @model_validator(mode="after")
    def validate_protocol(self) -> FrontendLlmServiceUpsertRequest:
        if self.protocol not in _LLM_PROVIDER_CATALOG:
            raise ValueError(f"unsupported llm protocol '{self.protocol}'")
        return self


class FrontendLlmServiceMutationResult(FrontendModel):
    action: str = Field(min_length=1)
    service_id: str = Field(min_length=1)


class FrontendLlmServiceActivateRequest(FrontendModel):
    service_id: str = Field(min_length=1)
    model: str | None = None


class FrontendLlmServiceActivationResult(FrontendModel):
    service_id: str = Field(min_length=1)
    protocol: str = Field(min_length=1)
    model: str = Field(min_length=1)


class FrontendLlmServiceDeleteRequest(FrontendModel):
    service_id: str = Field(min_length=1)


class FrontendLlmModelDiscoveryRequest(FrontendModel):
    service_id: str = Field(min_length=1)


class FrontendLlmModelDiscoveryResult(FrontendModel):
    service_id: str = Field(min_length=1)
    protocol: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    models: list[str] = Field(default_factory=list)
    active_model: str | None = None


class FrontendSettingsPage(FrontendModel):
    runtime: FrontendRuntimeSettingsView
    provider: FrontendProviderSettingsView
    llm: FrontendLlmSettingsView = Field(default_factory=FrontendLlmSettingsView)
    options: FrontendSettingsOptionCatalog
    snapshot_state: FrontendSettingsSnapshotState


class FrontendSettingsChange(FrontendModel):
    key: str = Field(min_length=1)
    before: str | bool
    after: str | bool


class FrontendSettingsSnapshot(FrontendModel):
    snapshot_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    request: FrontendSettingsUpdateRequest
    changed_keys: list[str] = Field(default_factory=list)
    applied_env_overrides: dict[str, str] = Field(default_factory=dict)
    backend_override: str | None = None
    restart_required: bool = True


class FrontendSettingsSnapshotState(FrontendModel):
    current_snapshot: FrontendSettingsSnapshot | None = None
    previous_snapshot: FrontendSettingsSnapshot | None = None
    restore_available: bool = False


class FrontendPersistedRuntimeState(FrontendModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    endpoint: str | None = None
    dev_mode: bool = False
    source: str = Field(default="persisted", min_length=1)
    source_service_id: str | None = None


class FrontendSettingsPreview(FrontendModel):
    request: FrontendSettingsUpdateRequest
    changed_keys: list[str] = Field(default_factory=list)
    changes: list[FrontendSettingsChange] = Field(default_factory=list)
    applied_env_overrides: dict[str, str] = Field(default_factory=dict)
    backend_override: str | None = None
    restart_required: bool = True
    preview: FrontendSettingsPage


class FrontendSettingsMutationResult(FrontendModel):
    action: str = Field(min_length=1)
    current_snapshot: FrontendSettingsSnapshot
    previous_snapshot: FrontendSettingsSnapshot | None = None
    restore_available: bool = False
    preview: FrontendSettingsPreview


def build_frontend_settings_page(
    config_summary: dict[str, Any],
    provider_status: dict[str, Any],
    *,
    llm_state: Mapping[str, Any] | None = None,
    snapshot_state: FrontendSettingsSnapshotState | dict[str, Any] | None = None,
    runtime_scope: str = "process",
    runtime_source: str = "env",
    runtime_source_service_id: str | None = None,
) -> FrontendSettingsPage:
    """Project product/app config payloads into the frontend-facing settings contract."""

    resolved_snapshot_state = _coerce_snapshot_state(snapshot_state)
    runtime = FrontendRuntimeSettingsView(
        backend=str(config_summary["backend"]),
        profile=str(config_summary["profile"]),
        backend_source=str(config_summary["backend_source"]),
        profile_source=str(config_summary["profile_source"]),
        scope=runtime_scope,
        source=runtime_source,
        dev_mode=bool(config_summary["dev_mode"]),
        dev_telemetry_configured=bool(config_summary["dev_telemetry_configured"]),
        debug_available=bool(config_summary["dev_mode"]),
    )
    provider = FrontendProviderSettingsView(
        provider=str(provider_status["provider"]),
        provider_family=str(provider_status["provider_family"]),
        model=str(provider_status["model"]),
        endpoint=(
            str(provider_status["endpoint"])
            if provider_status.get("endpoint") is not None
            else None
        ),
        source_service_id=runtime_source_service_id,
        timeout_ms=int(provider_status.get("timeout_ms", 30_000)),
        retry_policy=str(provider_status.get("retry_policy", "default")),
        status=str(provider_status["status"]),
        execution=str(provider_status["execution"]),
        auth_configured=bool(provider_status["auth"]["configured"]),
        auth_mode=str(provider_status["auth"].get("mode", "none")),
        auth_secret_env=(
            str(provider_status["auth"]["secret_env"])
            if provider_status["auth"].get("secret_env") is not None
            else None
        ),
        auth_parameter_name=(
            str(provider_status["auth"]["parameter_name"])
            if provider_status["auth"].get("parameter_name") is not None
            else None
        ),
        supported_capabilities=[str(item) for item in provider_status["supported_capabilities"]],
    )
    resolved_llm_state = load_frontend_llm_state(
        {_FRONTEND_LLM_STATE_PREFERENCE_KEY: llm_state} if llm_state is not None else None
    )
    runtime_active_service_id = runtime_source_service_id or _resolve_runtime_service_id(
        resolved_llm_state,
        provider.provider if provider.provider_family != "deterministic" else None,
        provider.endpoint,
    )
    options = FrontendSettingsOptionCatalog(
        backends=[backend.value for backend in CliBackend],
        profiles=[profile.value for profile in CliProfile],
        provider_families=[provider_family.value for provider_family in CapabilityProviderFamily],
        editable_keys=["provider", "model", "endpoint", "api_key", "dev_mode"],
    )
    return FrontendSettingsPage(
        runtime=runtime,
        provider=provider,
        llm=FrontendLlmSettingsView(
            selected_service_id=resolved_llm_state.get("selected_service_id"),
            active_service_id=runtime_active_service_id,
            protocols=[
                FrontendLlmProtocolView(
                    protocol=protocol,
                    label=str(protocol_meta["label"]),
                    default_name=str(protocol_meta["default_name"]),
                    default_icon=str(protocol_meta["default_icon"]),
                    default_endpoint=str(protocol_meta["default_endpoint"]),
                    auth_mode=str(protocol_meta["auth_mode"]),
                )
                for protocol, protocol_meta in _LLM_PROVIDER_CATALOG.items()
            ],
            services=[
                FrontendLlmServiceView(
                    service_id=str(service["service_id"]),
                    protocol=str(service["protocol"]),
                    name=str(service["name"]),
                    icon=str(service["icon"]) if service.get("icon") is not None else None,
                    endpoint=str(service["endpoint"]),
                    uses_official_endpoint=(
                        str(service["endpoint"])
                        == str(_LLM_PROVIDER_CATALOG[str(service["protocol"])]["default_endpoint"])
                    ),
                    api_key_saved=bool(service.get("api_key")),
                    api_key_masked=_mask_frontend_secret(service.get("api_key")),
                    active_model=(
                        str(service["active_model"])
                        if service.get("active_model") is not None
                        else None
                    ),
                    model_options=[str(item) for item in service.get("model_options", [])],
                    models_synced=bool(service.get("model_options")),
                    is_active=str(service["service_id"]) == runtime_active_service_id,
                )
                for service in resolved_llm_state["services"]
            ],
        ),
        options=options,
        snapshot_state=resolved_snapshot_state,
    )


def preview_frontend_settings_update(
    update_request: FrontendSettingsUpdateRequest | dict[str, Any],
    *,
    current_config: ResolvedCliConfig,
    env: Mapping[str, str] | None = None,
    llm_state: Mapping[str, Any] | None = None,
) -> FrontendSettingsPreview:
    """Preview a frontend settings mutation without mutating the live runtime."""

    request = (
        update_request
        if isinstance(update_request, FrontendSettingsUpdateRequest)
        else FrontendSettingsUpdateRequest.model_validate(update_request)
    )
    active_env = dict(env or environ)
    preview_env = dict(active_env)
    applied_env_overrides: dict[str, str] = {}
    if request.profile is not None:
        applied_env_overrides["MIND_CLI_PROFILE"] = request.profile
        preview_env["MIND_CLI_PROFILE"] = request.profile
    if request.provider is not None:
        applied_env_overrides["MIND_PROVIDER"] = request.provider
        preview_env["MIND_PROVIDER"] = request.provider
    if request.model is not None:
        applied_env_overrides["MIND_MODEL"] = request.model
        preview_env["MIND_MODEL"] = request.model
    if request.endpoint is not None:
        provider_for_endpoint = (
            request.provider
            or preview_env.get("MIND_PROVIDER")
            or active_env.get("MIND_PROVIDER")
            or "stub"
        )
        if request.endpoint.strip():
            preview_env["MIND_PROVIDER_ENDPOINT"] = resolve_frontend_llm_runtime_endpoint(
                provider_for_endpoint,
                request.endpoint.strip(),
            )
            applied_env_overrides["MIND_PROVIDER_ENDPOINT"] = preview_env["MIND_PROVIDER_ENDPOINT"]
        else:
            applied_env_overrides["MIND_PROVIDER_ENDPOINT"] = "(official default)"
            preview_env.pop("MIND_PROVIDER_ENDPOINT", None)
    if request.api_key is not None and request.api_key.strip():
        secret_env = provider_secret_env(
            request.provider
            or preview_env.get("MIND_PROVIDER")
            or active_env.get("MIND_PROVIDER")
            or "stub"
        )
        if secret_env is not None:
            applied_env_overrides[secret_env] = "***redacted***"
            preview_env.pop("MIND_PROVIDER_API_KEY", None)
            preview_env[secret_env] = request.api_key.strip()
    if request.dev_mode is not None:
        applied_env_overrides["MIND_DEV_MODE"] = "true" if request.dev_mode else "false"
        preview_env["MIND_DEV_MODE"] = applied_env_overrides["MIND_DEV_MODE"]

    resolved_llm_state = load_frontend_llm_state(
        {_FRONTEND_LLM_STATE_PREFERENCE_KEY: llm_state} if llm_state is not None else None
    )
    preview_llm_state = apply_frontend_llm_state_update(resolved_llm_state, request)

    preview_config = resolve_cli_config(
        profile=request.profile or current_config.requested_profile.value,
        backend=request.backend,
        sqlite_path=current_config.sqlite_path,
        postgres_dsn=current_config.postgres_dsn,
        allow_sqlite=True,
        env=preview_env,
    )
    current_page = build_frontend_settings_page(
        build_config_summary_payload(current_config, env=active_env),
        build_provider_status_payload(resolve_capability_provider_config(env=active_env)),
        llm_state=resolved_llm_state,
    )
    preview_page = build_frontend_settings_page(
        build_config_summary_payload(preview_config, env=preview_env),
        build_provider_status_payload(resolve_capability_provider_config(env=preview_env)),
        llm_state=preview_llm_state,
    )

    current_values = _settings_value_map(current_page)
    preview_values = _settings_value_map(preview_page)
    changes = [
        FrontendSettingsChange(key=key, before=current_values[key], after=preview_values[key])
        for key in _PREVIEWABLE_SETTINGS_KEYS
        if current_values[key] != preview_values[key]
    ]
    restart_required = bool(request.backend is not None or request.profile is not None)
    return FrontendSettingsPreview(
        request=request,
        changed_keys=[change.key for change in changes],
        changes=changes,
        applied_env_overrides=applied_env_overrides,
        backend_override=request.backend,
        restart_required=restart_required,
        preview=preview_page,
    )


def build_frontend_settings_snapshot(
    preview: FrontendSettingsPreview | dict[str, Any],
    *,
    snapshot_id: str,
    action: str,
) -> FrontendSettingsSnapshot:
    """Build a persistent snapshot record from one validated preview."""

    resolved_preview = (
        preview
        if isinstance(preview, FrontendSettingsPreview)
        else FrontendSettingsPreview.model_validate(preview)
    )
    return FrontendSettingsSnapshot(
        snapshot_id=snapshot_id,
        action=action,
        request=resolved_preview.request.model_copy(update={"api_key": None}),
        changed_keys=list(resolved_preview.changed_keys),
        applied_env_overrides=dict(resolved_preview.applied_env_overrides),
        backend_override=resolved_preview.backend_override,
        restart_required=resolved_preview.restart_required,
    )


def build_frontend_settings_mutation_result(
    *,
    action: str,
    current_snapshot: FrontendSettingsSnapshot | dict[str, Any],
    previous_snapshot: FrontendSettingsSnapshot | dict[str, Any] | None,
    preview: FrontendSettingsPreview | dict[str, Any],
) -> FrontendSettingsMutationResult:
    """Build the stable frontend-facing apply/restore response payload."""

    resolved_current = _coerce_snapshot(current_snapshot)
    assert resolved_current is not None
    resolved_previous = _coerce_snapshot(previous_snapshot)
    return FrontendSettingsMutationResult(
        action=action,
        current_snapshot=resolved_current,
        previous_snapshot=resolved_previous,
        restore_available=resolved_previous is not None,
        preview=(
            preview
            if isinstance(preview, FrontendSettingsPreview)
            else FrontendSettingsPreview.model_validate(preview)
        ),
    )


def load_frontend_settings_snapshot_state(
    preferences: Mapping[str, Any] | None,
) -> FrontendSettingsSnapshotState:
    """Load the persisted frontend settings snapshot state from user preferences."""

    raw_state = (
        preferences.get(_FRONTEND_SETTINGS_STATE_PREFERENCE_KEY)
        if isinstance(preferences, Mapping)
        else None
    )
    return _coerce_snapshot_state(raw_state)


def dump_frontend_settings_snapshot_state(
    snapshot_state: FrontendSettingsSnapshotState | dict[str, Any],
) -> dict[str, Any]:
    """Serialize the persisted frontend settings snapshot state for preferences."""

    resolved_state = _coerce_snapshot_state(snapshot_state)
    return {_FRONTEND_SETTINGS_STATE_PREFERENCE_KEY: resolved_state.model_dump(mode="json")}


def load_frontend_llm_state(
    preferences: Mapping[str, Any] | None,
) -> dict[str, Any]:
    raw_state = (
        preferences.get(_FRONTEND_LLM_STATE_PREFERENCE_KEY)
        if isinstance(preferences, Mapping)
        else None
    )
    raw_state = raw_state if isinstance(raw_state, Mapping) else {}
    services = _load_llm_services(raw_state)
    active_service_id = str(raw_state.get("active_service_id") or "") or None
    if active_service_id not in {service["service_id"] for service in services}:
        active_service_id = None
    selected_service_id = str(raw_state.get("selected_service_id") or "") or None
    if selected_service_id not in {service["service_id"] for service in services}:
        selected_service_id = active_service_id or (services[0]["service_id"] if services else None)
    return {
        "selected_service_id": selected_service_id,
        "active_service_id": active_service_id,
        "services": services,
    }


def dump_frontend_llm_state(
    llm_state: Mapping[str, Any],
) -> dict[str, Any]:
    resolved = load_frontend_llm_state({_FRONTEND_LLM_STATE_PREFERENCE_KEY: llm_state})
    return {
        _FRONTEND_LLM_STATE_PREFERENCE_KEY: resolved,
    }


def apply_frontend_llm_state_update(
    llm_state: Mapping[str, Any] | None,
    update_request: FrontendSettingsUpdateRequest | Mapping[str, Any],
) -> dict[str, Any]:
    request = (
        update_request
        if isinstance(update_request, FrontendSettingsUpdateRequest)
        else FrontendSettingsUpdateRequest.model_validate(update_request)
    )
    resolved = load_frontend_llm_state({_FRONTEND_LLM_STATE_PREFERENCE_KEY: llm_state})
    service = find_frontend_llm_service(
        resolved,
        service_id=request.service_id,
        protocol=request.provider,
    )
    if service is None:
        if request.provider in {"stub", "deterministic"}:
            resolved["active_service_id"] = None
            return resolved
        if request.provider not in _LLM_PROVIDER_CATALOG:
            return resolved
        auto_service = {
            "service_id": f"managed-{request.provider}",
            "protocol": request.provider,
            "name": _default_llm_name(request.provider),
            "icon": _default_llm_icon(request.provider),
            "endpoint": _resolve_llm_provider_endpoint(request.provider, request.endpoint),
            "api_key": request.api_key.strip()
            if request.api_key and request.api_key.strip()
            else None,
            "active_model": request.model.strip()
            if request.model and request.model.strip()
            else None,
            "model_options": [request.model.strip()]
            if request.model and request.model.strip()
            else [],
        }
        resolved["services"] = [
            service_item
            for service_item in resolved["services"]
            if service_item["service_id"] != auto_service["service_id"]
        ] + [auto_service]
        resolved["selected_service_id"] = auto_service["service_id"]
        resolved["active_service_id"] = auto_service["service_id"]
        return resolved

    next_services: list[dict[str, Any]] = []
    for current in resolved["services"]:
        if current["service_id"] != service["service_id"]:
            next_services.append(dict(current))
            continue
        updated = dict(current)
        if request.model is not None:
            updated["active_model"] = request.model
            if request.model not in updated["model_options"]:
                updated["model_options"] = [request.model, *updated["model_options"]]
        if request.endpoint is not None:
            updated["endpoint"] = _resolve_llm_provider_endpoint(
                str(updated["protocol"]),
                request.endpoint,
            )
        if request.api_key is not None and request.api_key.strip():
            updated["api_key"] = request.api_key.strip()
        next_services.append(updated)
    resolved["services"] = next_services
    resolved["selected_service_id"] = service["service_id"]
    resolved["active_service_id"] = service["service_id"]
    return resolved


def _settings_value_map(page: FrontendSettingsPage) -> dict[str, str | bool]:
    return {
        "backend": page.runtime.backend,
        "profile": page.runtime.profile,
        "provider": page.provider.provider,
        "model": page.provider.model,
        "endpoint": page.provider.endpoint or "",
        "dev_mode": page.runtime.dev_mode,
    }


def frontend_llm_provider_catalog() -> dict[str, dict[str, Any]]:
    return {
        provider: {
            **meta,
            "models": list(meta["models"]),
        }
        for provider, meta in _LLM_PROVIDER_CATALOG.items()
    }


def provider_secret_env(provider: str) -> str | None:
    provider_meta = _LLM_PROVIDER_CATALOG.get(provider)
    if provider_meta is None:
        return None
    return str(provider_meta["secret_env"])


def _mask_frontend_secret(raw_value: Any) -> str | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    if len(value) <= 6:
        return f"{value[:1]}***{value[-1:]}"
    if len(value) <= 12:
        return f"{value[:2]}***{value[-2:]}"
    return f"{value[:4]}***{value[-4:]}"


def find_frontend_llm_service(
    llm_state: Mapping[str, Any] | None,
    *,
    service_id: str | None = None,
    protocol: str | None = None,
) -> dict[str, Any] | None:
    resolved = load_frontend_llm_state({_FRONTEND_LLM_STATE_PREFERENCE_KEY: llm_state})
    if service_id is not None:
        for service in resolved["services"]:
            if service["service_id"] == service_id:
                return dict(service)
        return None
    if protocol is not None:
        active_service_id = resolved.get("active_service_id")
        if active_service_id is not None:
            for service in resolved["services"]:
                if service["service_id"] == active_service_id and service["protocol"] == protocol:
                    return dict(service)
        for service in resolved["services"]:
            if service["protocol"] == protocol:
                return dict(service)
    return None


def upsert_frontend_llm_service(
    llm_state: Mapping[str, Any] | None,
    request_payload: FrontendLlmServiceUpsertRequest | Mapping[str, Any],
    *,
    new_service_id: str,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    request = (
        request_payload
        if isinstance(request_payload, FrontendLlmServiceUpsertRequest)
        else FrontendLlmServiceUpsertRequest.model_validate(request_payload)
    )
    resolved = load_frontend_llm_state({_FRONTEND_LLM_STATE_PREFERENCE_KEY: llm_state})
    existing = (
        find_frontend_llm_service(resolved, service_id=request.service_id)
        if request.service_id
        else None
    )
    service_id = request.service_id or f"svc-{new_service_id}"
    protocol = request.protocol
    service = {
        "service_id": service_id,
        "protocol": protocol,
        "name": (request.name or "").strip() or _default_llm_name(protocol),
        "icon": (request.icon or "").strip() or None,
        "endpoint": _resolve_llm_provider_endpoint(protocol, request.endpoint),
        "api_key": (
            request.api_key.strip()
            if isinstance(request.api_key, str) and request.api_key.strip()
            else (existing.get("api_key") if existing is not None else None)
        ),
        "active_model": (
            request.model.strip()
            if isinstance(request.model, str) and request.model.strip()
            else (existing.get("active_model") if existing is not None else None)
        ),
        "model_options": list(existing.get("model_options", [])) if existing is not None else [],
    }
    model_options = service["model_options"]
    assert isinstance(model_options, list)
    if service["active_model"] and service["active_model"] not in model_options:
        service["model_options"] = [service["active_model"], *model_options]
    next_services: list[dict[str, Any]] = []
    replaced = False
    for current in resolved["services"]:
        if current["service_id"] != service_id:
            next_services.append(dict(current))
            continue
        next_services.append(service)
        replaced = True
    if not replaced:
        next_services.append(service)
    resolved["services"] = next_services
    resolved["selected_service_id"] = service_id
    if resolved.get("active_service_id") == service_id and service["active_model"] is None:
        resolved["active_service_id"] = None
    return resolved, service, "updated" if replaced else "created"


def remember_frontend_llm_models(
    llm_state: Mapping[str, Any] | None,
    *,
    service_id: str,
    models: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = load_frontend_llm_state({_FRONTEND_LLM_STATE_PREFERENCE_KEY: llm_state})
    unique_models = _dedupe_strings(models)
    if not unique_models:
        raise RuntimeError("no models were returned by the provider")
    next_services: list[dict[str, Any]] = []
    remembered: dict[str, Any] | None = None
    for current in resolved["services"]:
        if current["service_id"] != service_id:
            next_services.append(dict(current))
            continue
        updated = dict(current)
        updated["model_options"] = unique_models
        if updated.get("active_model") not in unique_models:
            updated["active_model"] = unique_models[0]
        remembered = updated
        next_services.append(updated)
    if remembered is None:
        raise RuntimeError("requested llm service was not found")
    resolved["services"] = next_services
    resolved["selected_service_id"] = service_id
    return resolved, remembered


def activate_frontend_llm_service(
    llm_state: Mapping[str, Any] | None,
    request_payload: FrontendLlmServiceActivateRequest | Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    request = (
        request_payload
        if isinstance(request_payload, FrontendLlmServiceActivateRequest)
        else FrontendLlmServiceActivateRequest.model_validate(request_payload)
    )
    resolved = load_frontend_llm_state({_FRONTEND_LLM_STATE_PREFERENCE_KEY: llm_state})
    next_services: list[dict[str, Any]] = []
    activated: dict[str, Any] | None = None
    for current in resolved["services"]:
        updated = dict(current)
        if current["service_id"] == request.service_id:
            selected_model = (
                request.model
                or updated.get("active_model")
                or (updated["model_options"][0] if updated["model_options"] else None)
            )
            if not selected_model:
                raise RuntimeError("请先拉取模型列表，再启用这个服务。")
            if updated["model_options"] and selected_model not in updated["model_options"]:
                raise RuntimeError("当前服务没有这个模型，请先刷新模型列表。")
            updated["active_model"] = selected_model
            activated = updated
        next_services.append(updated)
    if activated is None:
        raise RuntimeError("requested llm service was not found")
    resolved["services"] = next_services
    resolved["selected_service_id"] = activated["service_id"]
    resolved["active_service_id"] = activated["service_id"]
    return resolved, activated


def delete_frontend_llm_service(
    llm_state: Mapping[str, Any] | None,
    request_payload: FrontendLlmServiceDeleteRequest | Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    request = (
        request_payload
        if isinstance(request_payload, FrontendLlmServiceDeleteRequest)
        else FrontendLlmServiceDeleteRequest.model_validate(request_payload)
    )
    resolved = load_frontend_llm_state({_FRONTEND_LLM_STATE_PREFERENCE_KEY: llm_state})
    deleted = find_frontend_llm_service(resolved, service_id=request.service_id)
    if deleted is None:
        raise RuntimeError("requested llm service was not found")

    next_services = [
        dict(current)
        for current in resolved["services"]
        if current["service_id"] != request.service_id
    ]
    deleted_was_active = resolved.get("active_service_id") == request.service_id
    resolved["services"] = next_services
    if deleted_was_active:
        resolved["active_service_id"] = None

    remaining_ids = {service["service_id"] for service in next_services}
    if resolved.get("selected_service_id") not in remaining_ids:
        resolved["selected_service_id"] = resolved.get("active_service_id") or (
            next_services[0]["service_id"] if next_services else None
        )
    return resolved, deleted, deleted_was_active


def discover_frontend_llm_models(
    service: Mapping[str, Any],
) -> list[str]:
    protocol = str(service["protocol"])
    api_key = str(service.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("请先为这个服务填写 API Key。")
    request_endpoint = _llm_models_endpoint(protocol, str(service["endpoint"]))
    headers = _llm_model_headers(protocol, api_key)
    request = Request(request_endpoint, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=10.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"拉取模型列表失败（HTTP {exc.code}）。") from exc
    except URLError as exc:
        raise RuntimeError("当前无法连接到模型服务。") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("模型服务返回了无法识别的内容。") from exc
    models = _parse_llm_models(protocol, payload)
    if not models:
        raise RuntimeError("当前服务没有返回可用模型。")
    return models


_PREVIEWABLE_SETTINGS_KEYS = ("backend", "profile", "provider", "model", "endpoint", "dev_mode")
_FRONTEND_SETTINGS_STATE_PREFERENCE_KEY = "frontend_settings_state"
_FRONTEND_LLM_STATE_PREFERENCE_KEY = "frontend_llm_state"
_FRONTEND_RUNTIME_STATE_PREFERENCE_KEY = "frontend_runtime_state"


def load_frontend_runtime_state(
    preferences: Mapping[str, Any] | None,
) -> FrontendPersistedRuntimeState | None:
    raw_state = (
        preferences.get(_FRONTEND_RUNTIME_STATE_PREFERENCE_KEY)
        if isinstance(preferences, Mapping)
        else None
    )
    if not isinstance(raw_state, Mapping):
        return None
    try:
        return FrontendPersistedRuntimeState.model_validate(raw_state)
    except Exception:
        return None


def dump_frontend_runtime_state(
    runtime_state: FrontendPersistedRuntimeState | Mapping[str, Any],
) -> dict[str, Any]:
    resolved = (
        runtime_state
        if isinstance(runtime_state, FrontendPersistedRuntimeState)
        else FrontendPersistedRuntimeState.model_validate(runtime_state)
    )
    return {_FRONTEND_RUNTIME_STATE_PREFERENCE_KEY: resolved.model_dump(mode="json")}


def _load_llm_services(raw_state: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_services = raw_state.get("services")
    if isinstance(raw_services, list):
        services = [
            normalized
            for item in raw_services
            if isinstance(item, Mapping)
            for normalized in [_normalize_llm_service(item)]
            if normalized is not None
        ]
        if services:
            return services
    return _migrate_legacy_llm_services(raw_state)


def _normalize_llm_service(raw_service: Mapping[str, Any]) -> dict[str, Any] | None:
    protocol = str(raw_service.get("protocol") or raw_service.get("provider") or "").strip()
    if protocol not in _LLM_PROVIDER_CATALOG:
        return None
    service_id = str(raw_service.get("service_id") or raw_service.get("id") or "").strip()
    if not service_id:
        return None
    active_model = (
        str(raw_service.get("active_model") or raw_service.get("model") or "").strip() or None
    )
    model_options = _dedupe_strings(
        raw_service.get("model_options") or raw_service.get("models") or []
    )
    if active_model and active_model not in model_options:
        model_options = [active_model, *model_options]
    api_key = raw_service.get("api_key")
    return {
        "service_id": service_id,
        "protocol": protocol,
        "name": str(raw_service.get("name") or _default_llm_name(protocol)).strip(),
        "icon": str(raw_service.get("icon")).strip() or None
        if raw_service.get("icon") is not None
        else None,
        "endpoint": _resolve_llm_provider_endpoint(protocol, raw_service.get("endpoint")),
        "api_key": api_key if isinstance(api_key, str) and api_key else None,
        "active_model": active_model,
        "model_options": model_options,
    }


def _migrate_legacy_llm_services(raw_state: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_providers = raw_state.get("providers")
    if not isinstance(raw_providers, Mapping):
        return []
    selected_provider = str(raw_state.get("selected_provider") or "").strip()
    services: list[dict[str, Any]] = []
    for provider_name, raw_provider in raw_providers.items():
        if provider_name not in _LLM_PROVIDER_CATALOG or not isinstance(raw_provider, Mapping):
            continue
        api_key = raw_provider.get("api_key")
        endpoint = raw_provider.get("endpoint")
        model = str(raw_provider.get("model") or "").strip()
        has_saved_values = bool(api_key) or endpoint not in (None, "") or bool(model)
        if not has_saved_values and provider_name != selected_provider:
            continue
        model_options = _dedupe_strings(
            [model, *_LLM_PROVIDER_CATALOG[provider_name]["models"]]
            if model
            else _LLM_PROVIDER_CATALOG[provider_name]["models"]
        )
        services.append(
            {
                "service_id": f"legacy-{provider_name}",
                "protocol": provider_name,
                "name": _default_llm_name(provider_name),
                "icon": _default_llm_icon(provider_name),
                "endpoint": _resolve_llm_provider_endpoint(provider_name, endpoint),
                "api_key": api_key if isinstance(api_key, str) and api_key else None,
                "active_model": model or (model_options[0] if model_options else None),
                "model_options": model_options,
            }
        )
    return services


def _resolve_runtime_service_id(
    llm_state: Mapping[str, Any],
    protocol: str | None,
    endpoint: str | None,
) -> str | None:
    if protocol is None:
        return None
    active_service_id = llm_state.get("active_service_id")
    for service in llm_state.get("services", []):
        if (
            service["service_id"] == active_service_id
            and service["protocol"] == protocol
            and _service_matches_runtime_endpoint(service, endpoint)
        ):
            return service["service_id"]
    if endpoint is not None:
        for service in llm_state.get("services", []):
            if service["protocol"] == protocol and _service_matches_runtime_endpoint(
                service, endpoint
            ):
                return service["service_id"]
    for service in llm_state.get("services", []):
        if service["protocol"] == protocol:
            return service["service_id"]
    return None


def _dedupe_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    deduped: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def _default_llm_name(protocol: str) -> str:
    return str(_LLM_PROVIDER_CATALOG[protocol]["default_name"])


def _default_llm_icon(protocol: str) -> str:
    return str(_LLM_PROVIDER_CATALOG[protocol]["default_icon"])


def _default_llm_endpoint(protocol: str) -> str:
    return str(_LLM_PROVIDER_CATALOG[protocol]["default_endpoint"])


def _resolve_llm_provider_endpoint(provider: str, stored_endpoint: Any) -> str:
    base = str(stored_endpoint).strip() if isinstance(stored_endpoint, str) else ""
    if not base:
        return _default_llm_endpoint(provider)
    parts = urlsplit(base)
    if not parts.scheme or not parts.netloc:
        return _default_llm_endpoint(provider)
    path = _strip_llm_endpoint_suffix(provider, parts.path.rstrip("/"))
    official_parts = urlsplit(_default_llm_endpoint(provider))
    if not path and parts.netloc == official_parts.netloc:
        path = official_parts.path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def resolve_frontend_llm_runtime_endpoint(provider: str, stored_endpoint: Any) -> str:
    if provider not in _LLM_PROVIDER_CATALOG:
        return str(stored_endpoint).strip() if isinstance(stored_endpoint, str) else ""
    base = _resolve_llm_provider_endpoint(provider, stored_endpoint)
    parts = urlsplit(base)
    path = parts.path.rstrip("/")
    if provider == "openai":
        next_path = f"{path}/chat/completions" if path else "/chat/completions"
    elif provider == "claude":
        next_path = f"{path}/messages" if path else "/v1/messages"
    else:
        next_path = f"{path}/models" if path else "/v1beta/models"
    return urlunsplit((parts.scheme, parts.netloc, next_path, "", ""))


def _llm_models_endpoint(protocol: str, endpoint: str) -> str:
    parts = urlsplit(_resolve_llm_provider_endpoint(protocol, endpoint))
    path = parts.path.rstrip("/")
    if protocol == "openai":
        if path.endswith("/models"):
            next_path = path
        elif path.endswith("/v1"):
            next_path = f"{path}/models"
        elif not path:
            next_path = "/v1/models"
        else:
            next_path = f"{path}/models"
        return urlunsplit((parts.scheme, parts.netloc, next_path, "", ""))
    if protocol == "claude":
        if path.endswith("/models"):
            next_path = path
        elif path.endswith("/v1"):
            next_path = f"{path}/models"
        elif not path:
            next_path = "/v1/models"
        else:
            next_path = f"{path}/models"
        return urlunsplit((parts.scheme, parts.netloc, next_path, "", ""))
    if path.endswith("/models"):
        next_path = path
    elif not path:
        next_path = "/v1beta/models"
    else:
        next_path = f"{path}/models"
    return urlunsplit((parts.scheme, parts.netloc, next_path, "", ""))


def _strip_llm_endpoint_suffix(provider: str, path: str) -> str:
    if provider == "openai":
        for suffix in ("/responses", "/chat/completions", "/completions", "/models"):
            if path.endswith(suffix):
                return path[: -len(suffix)]
        return path
    if provider == "claude":
        for suffix in ("/messages", "/models"):
            if path.endswith(suffix):
                return path[: -len(suffix)]
        return path
    cleaned_path = path
    if ":generateContent" in cleaned_path:
        cleaned_path = cleaned_path.split(":generateContent", 1)[0]
    if "/models/" in cleaned_path:
        return cleaned_path.split("/models/", 1)[0]
    if cleaned_path.endswith("/models"):
        return cleaned_path[: -len("/models")]
    return cleaned_path


def _service_matches_runtime_endpoint(
    service: Mapping[str, Any], runtime_endpoint: str | None
) -> bool:
    if runtime_endpoint is None:
        return False
    return resolve_frontend_llm_runtime_endpoint(
        str(service["protocol"]),
        str(service["endpoint"]),
    ) == str(runtime_endpoint)


def _llm_model_headers(protocol: str, api_key: str) -> dict[str, str]:
    if protocol == "openai":
        return {"Authorization": f"Bearer {api_key}"}
    if protocol == "claude":
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    return {"x-goog-api-key": api_key}


def _parse_llm_models(protocol: str, payload: Mapping[str, Any]) -> list[str]:
    if protocol in {"openai", "claude"}:
        models = []
        for item in payload.get("data", []):
            if not isinstance(item, Mapping):
                continue
            model_id = str(item.get("id") or item.get("name") or "").strip()
            if model_id and model_id not in models:
                models.append(model_id)
        return models
    models = []
    for item in payload.get("models", []):
        if not isinstance(item, Mapping):
            continue
        raw_name = str(item.get("name") or item.get("baseModelId") or "").strip()
        model_id = raw_name.split("/")[-1] if "/" in raw_name else raw_name
        if model_id and model_id not in models:
            models.append(model_id)
    return models


def _coerce_snapshot_state(
    snapshot_state: FrontendSettingsSnapshotState | dict[str, Any] | None,
) -> FrontendSettingsSnapshotState:
    if isinstance(snapshot_state, FrontendSettingsSnapshotState):
        current_snapshot = snapshot_state.current_snapshot
        previous_snapshot = snapshot_state.previous_snapshot
    elif isinstance(snapshot_state, Mapping):
        current_snapshot = _coerce_snapshot(snapshot_state.get("current_snapshot"))
        previous_snapshot = _coerce_snapshot(snapshot_state.get("previous_snapshot"))
    else:
        current_snapshot = None
        previous_snapshot = None
    return FrontendSettingsSnapshotState(
        current_snapshot=current_snapshot,
        previous_snapshot=previous_snapshot,
        restore_available=previous_snapshot is not None,
    )


def _coerce_snapshot(
    snapshot: FrontendSettingsSnapshot | dict[str, Any] | None,
) -> FrontendSettingsSnapshot | None:
    if snapshot is None:
        return None
    if isinstance(snapshot, FrontendSettingsSnapshot):
        return snapshot
    return FrontendSettingsSnapshot.model_validate(snapshot)
