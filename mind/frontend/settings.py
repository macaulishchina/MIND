"""Frontend-facing settings surface contracts for Phase M prework."""

from __future__ import annotations

from collections.abc import Mapping
from os import environ
from typing import Any

from pydantic import Field, model_validator

from mind.app.services.system import build_config_summary_payload, build_provider_status_payload
from mind.capabilities import CapabilityProviderFamily, resolve_capability_provider_config
from mind.cli_config import CliBackend, CliProfile, ResolvedCliConfig, resolve_cli_config

from .contracts import FrontendModel


class FrontendSettingsUpdateRequest(FrontendModel):
    """Frozen frontend-facing config mutation contract."""

    backend: str | None = None
    profile: str | None = None
    provider: str | None = None
    model: str | None = None
    dev_mode: bool | None = None

    @model_validator(mode="after")
    def enforce_non_empty(self) -> FrontendSettingsUpdateRequest:
        if (
            self.backend is None
            and self.profile is None
            and self.provider is None
            and self.model is None
            and self.dev_mode is None
        ):
            raise ValueError("frontend settings updates require at least one change")
        return self


class FrontendRuntimeSettingsView(FrontendModel):
    backend: str = Field(min_length=1)
    profile: str = Field(min_length=1)
    backend_source: str = Field(min_length=1)
    profile_source: str = Field(min_length=1)
    dev_mode: bool
    dev_telemetry_configured: bool
    debug_available: bool


class FrontendProviderSettingsView(FrontendModel):
    provider: str = Field(min_length=1)
    provider_family: str = Field(min_length=1)
    model: str = Field(min_length=1)
    endpoint: str | None = None
    status: str = Field(min_length=1)
    execution: str = Field(min_length=1)
    auth_configured: bool
    supported_capabilities: list[str] = Field(default_factory=list)


class FrontendSettingsOptionCatalog(FrontendModel):
    backends: list[str] = Field(default_factory=list)
    profiles: list[str] = Field(default_factory=list)
    provider_families: list[str] = Field(default_factory=list)
    editable_keys: list[str] = Field(default_factory=list)


class FrontendSettingsPage(FrontendModel):
    runtime: FrontendRuntimeSettingsView
    provider: FrontendProviderSettingsView
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
    snapshot_state: FrontendSettingsSnapshotState | dict[str, Any] | None = None,
) -> FrontendSettingsPage:
    """Project product/app config payloads into the frontend-facing settings contract."""

    resolved_snapshot_state = _coerce_snapshot_state(snapshot_state)
    runtime = FrontendRuntimeSettingsView(
        backend=str(config_summary["backend"]),
        profile=str(config_summary["profile"]),
        backend_source=str(config_summary["backend_source"]),
        profile_source=str(config_summary["profile_source"]),
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
        status=str(provider_status["status"]),
        execution=str(provider_status["execution"]),
        auth_configured=bool(provider_status["auth"]["configured"]),
        supported_capabilities=[str(item) for item in provider_status["supported_capabilities"]],
    )
    options = FrontendSettingsOptionCatalog(
        backends=[backend.value for backend in CliBackend],
        profiles=[profile.value for profile in CliProfile],
        provider_families=[provider_family.value for provider_family in CapabilityProviderFamily],
        editable_keys=["backend", "profile", "provider", "model", "dev_mode"],
    )
    return FrontendSettingsPage(
        runtime=runtime,
        provider=provider,
        options=options,
        snapshot_state=resolved_snapshot_state,
    )


def preview_frontend_settings_update(
    update_request: FrontendSettingsUpdateRequest | dict[str, Any],
    *,
    current_config: ResolvedCliConfig,
    env: Mapping[str, str] | None = None,
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
    if request.dev_mode is not None:
        applied_env_overrides["MIND_DEV_MODE"] = "true" if request.dev_mode else "false"
        preview_env["MIND_DEV_MODE"] = applied_env_overrides["MIND_DEV_MODE"]

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
    )
    preview_page = build_frontend_settings_page(
        build_config_summary_payload(preview_config, env=preview_env),
        build_provider_status_payload(resolve_capability_provider_config(env=preview_env)),
    )

    current_values = _settings_value_map(current_page)
    preview_values = _settings_value_map(preview_page)
    changes = [
        FrontendSettingsChange(key=key, before=current_values[key], after=preview_values[key])
        for key in _PREVIEWABLE_SETTINGS_KEYS
        if current_values[key] != preview_values[key]
    ]
    return FrontendSettingsPreview(
        request=request,
        changed_keys=[change.key for change in changes],
        changes=changes,
        applied_env_overrides=applied_env_overrides,
        backend_override=request.backend,
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
        request=resolved_preview.request,
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
    return {
        _FRONTEND_SETTINGS_STATE_PREFERENCE_KEY: resolved_state.model_dump(mode="json")
    }


def _settings_value_map(page: FrontendSettingsPage) -> dict[str, str | bool]:
    return {
        "backend": page.runtime.backend,
        "profile": page.runtime.profile,
        "provider": page.provider.provider,
        "model": page.provider.model,
        "dev_mode": page.runtime.dev_mode,
    }


_PREVIEWABLE_SETTINGS_KEYS = ("backend", "profile", "provider", "model", "dev_mode")
_FRONTEND_SETTINGS_STATE_PREFERENCE_KEY = "frontend_settings_state"


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
