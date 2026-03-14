"""Frontend-facing settings surface contracts (moved to app layer for architecture compliance)."""

from __future__ import annotations

from collections.abc import Mapping
from os import environ
from typing import Any

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



def _settings_value_map(page: FrontendSettingsPage) -> dict[str, str | bool]:
    return {
        "backend": page.runtime.backend,
        "profile": page.runtime.profile,
        "provider": page.provider.provider,
        "model": page.provider.model,
        "endpoint": page.provider.endpoint or "",
        "dev_mode": page.runtime.dev_mode,
    }


def _mask_frontend_secret(raw_value: Any) -> str | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    if len(value) <= 6:
        return f"{value[:1]}***{value[-1:]}"
    if len(value) <= 12:
        return f"{value[:2]}***{value[-2:]}"
    return f"{value[:4]}***{value[-4:]}"

_PREVIEWABLE_SETTINGS_KEYS = ("backend", "profile", "provider", "model", "endpoint", "dev_mode")
_FRONTEND_SETTINGS_STATE_PREFERENCE_KEY = "frontend_settings_state"
_FRONTEND_LLM_STATE_PREFERENCE_KEY = "frontend_llm_state"
_FRONTEND_RUNTIME_STATE_PREFERENCE_KEY = "frontend_runtime_state"


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

from mind.app.frontend_llm_services import (  # noqa: E402, I001
    activate_frontend_llm_service as activate_frontend_llm_service,
    apply_frontend_llm_state_update as apply_frontend_llm_state_update,
    delete_frontend_llm_service as delete_frontend_llm_service,
    discover_frontend_llm_models as discover_frontend_llm_models,
    dump_frontend_llm_state as dump_frontend_llm_state,
    dump_frontend_runtime_state as dump_frontend_runtime_state,
    find_frontend_llm_service as find_frontend_llm_service,
    frontend_llm_provider_catalog as frontend_llm_provider_catalog,
    load_frontend_llm_state as load_frontend_llm_state,
    load_frontend_runtime_state as load_frontend_runtime_state,
    provider_secret_env as provider_secret_env,
    remember_frontend_llm_models as remember_frontend_llm_models,
    resolve_frontend_llm_runtime_endpoint as resolve_frontend_llm_runtime_endpoint,
    _resolve_runtime_service_id as _resolve_runtime_service_id,
    upsert_frontend_llm_service as upsert_frontend_llm_service,
)
