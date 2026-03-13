"""Process-wide frontend/runtime provider state management."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from os import environ
from typing import Any

from mind.app.context import ExecutionPolicy, ProviderSelection
from mind.app.contracts import AppRequest, AppStatus
from mind.capabilities import resolve_capability_provider_config

_TRUE_ENV_VALUES = frozenset({"1", "true", "yes", "on"})
_LIVE_PROVIDER_ENV_KEYS = frozenset(
    {
        "MIND_PROVIDER",
        "MIND_MODEL",
        "MIND_PROVIDER_ENDPOINT",
        "MIND_PROVIDER_TIMEOUT_MS",
        "MIND_PROVIDER_RETRY_POLICY",
        "MIND_PROVIDER_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "MIND_DEV_MODE",
    }
)
_UNSET = object()

SYSTEM_RUNTIME_PRINCIPAL_ID = "system-runtime"
LEGACY_FRONTEND_RUNTIME_PRINCIPAL_ID = "frontend-user"
_BUILTIN_PROVIDERS = frozenset({"stub", "deterministic"})


@dataclass(frozen=True)
class GlobalRuntimeState:
    """Current process-wide runtime settings."""

    provider_selection: ProviderSelection
    dev_mode: bool
    source: str
    source_service_id: str | None = None


class GlobalRuntimeManager:
    """Persist and serve the process-wide provider/runtime selection."""

    def __init__(
        self,
        *,
        user_state_service: Any,
        current_config: Any,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._user_state_service = user_state_service
        self._current_config = current_config
        self._base_env = dict(env or environ)
        self._env = dict(self._base_env)
        provider_config = resolve_capability_provider_config(env=self._base_env)
        self._state = GlobalRuntimeState(
            provider_selection=ProviderSelection(
                provider=provider_config.provider,
                model=provider_config.model,
                endpoint=provider_config.endpoint,
                timeout_ms=provider_config.timeout_ms,
                retry_policy=provider_config.retry_policy,
            ),
            dev_mode=self._base_env.get("MIND_DEV_MODE", "").strip().lower() in _TRUE_ENV_VALUES,
            source="env",
            source_service_id=None,
        )
        self._bootstrapped = False

    def bootstrap(self) -> GlobalRuntimeState:
        if self._bootstrapped:
            return self._state

        from mind.frontend.settings import (
            FrontendSettingsUpdateRequest,
            find_frontend_llm_service,
            load_frontend_llm_state,
            load_frontend_runtime_state,
            load_frontend_settings_snapshot_state,
        )

        preferences, source = self._load_runtime_preferences()
        runtime_state = load_frontend_runtime_state(preferences)
        llm_state = load_frontend_llm_state(preferences)
        snapshot_state = load_frontend_settings_snapshot_state(preferences)

        if runtime_state is not None:
            self._apply_update_request(
                FrontendSettingsUpdateRequest(
                    provider=runtime_state.provider,
                    model=runtime_state.model,
                    endpoint=runtime_state.endpoint,
                    api_key=None,
                    dev_mode=runtime_state.dev_mode,
                    service_id=runtime_state.source_service_id,
                ),
                llm_state=llm_state,
                source=runtime_state.source or source,
                source_service_id=runtime_state.source_service_id,
                persist=False,
            )
        elif snapshot_state.current_snapshot is not None:
            self._apply_update_request(
                snapshot_state.current_snapshot.request,
                llm_state=llm_state,
                source=source,
                source_service_id=None,
                persist=True,
            )
        else:
            active_service_id = llm_state.get("active_service_id")
            active_service = (
                find_frontend_llm_service(llm_state, service_id=str(active_service_id))
                if active_service_id is not None
                else None
            )
            if active_service is not None:
                self.apply_service(
                    active_service,
                    llm_state=llm_state,
                    dev_mode=self._state.dev_mode,
                    source=source,
                    persist=True,
                )
            else:
                self.reset_to_env_defaults(source=source, persist=source != "env")
        self._bootstrapped = True
        return self._state

    def current_provider_selection(self) -> ProviderSelection:
        self.bootstrap()
        return self._state.provider_selection

    def current_provider_env(self) -> Mapping[str, str]:
        self.bootstrap()
        return dict(self._env)

    def current_dev_mode(self) -> bool:
        self.bootstrap()
        return self._state.dev_mode

    def current_source(self) -> str:
        self.bootstrap()
        return self._state.source

    def current_source_service_id(self) -> str | None:
        self.bootstrap()
        return self._state.source_service_id

    def apply_request_defaults(
        self,
        req: AppRequest,
        *,
        include_provider_selection: bool = True,
        respect_request_policy: bool = False,
    ) -> AppRequest:
        self.bootstrap()
        effective_dev_mode = (
            req.policy.dev_mode
            if respect_request_policy and req.policy is not None
            else self._state.dev_mode
        )
        policy = (
            req.policy.model_copy(update={"dev_mode": effective_dev_mode})
            if req.policy is not None
            else ExecutionPolicy(dev_mode=effective_dev_mode)
        )
        update: dict[str, Any] = {"policy": policy}
        if include_provider_selection and req.provider_selection is None:
            update["provider_selection"] = self._state.provider_selection
        return req.model_copy(update=update)

    def apply_builtin(
        self,
        *,
        dev_mode: bool | None = None,
        source: str = "persisted",
        persist: bool = True,
    ) -> GlobalRuntimeState:
        from mind.frontend.settings import FrontendSettingsUpdateRequest

        return self._apply_update_request(
            FrontendSettingsUpdateRequest(
                provider="deterministic",
                model="deterministic",
                dev_mode=self._state.dev_mode if dev_mode is None else bool(dev_mode),
            ),
            llm_state=None,
            source=source,
            source_service_id=None,
            persist=persist,
        )

    def apply_service(
        self,
        service: Mapping[str, Any],
        *,
        llm_state: Mapping[str, Any] | None,
        dev_mode: bool | None = None,
        source: str = "persisted",
        persist: bool = True,
    ) -> GlobalRuntimeState:
        from mind.frontend.settings import FrontendSettingsUpdateRequest

        return self._apply_update_request(
            FrontendSettingsUpdateRequest(
                service_id=str(service["service_id"]),
                provider=str(service["protocol"]),
                model=(
                    str(service["active_model"])
                    if service.get("active_model") is not None
                    else None
                ),
                endpoint=str(service["endpoint"]),
                api_key=(
                    str(service["api_key"])
                    if service.get("api_key") is not None
                    else None
                ),
                dev_mode=self._state.dev_mode if dev_mode is None else bool(dev_mode),
            ),
            llm_state=llm_state,
            source=source,
            source_service_id=str(service["service_id"]),
            persist=persist,
        )

    def update_active_service(
        self,
        service: Mapping[str, Any],
        *,
        llm_state: Mapping[str, Any] | None,
        dev_mode: bool | None = None,
        source: str = "persisted",
        persist: bool = True,
    ) -> GlobalRuntimeState:
        return self.apply_service(
            service,
            llm_state=llm_state,
            dev_mode=dev_mode,
            source=source,
            persist=persist,
        )

    def apply_update_request(
        self,
        update_request: Any,
        *,
        llm_state: Mapping[str, Any] | None = None,
        source: str = "persisted",
        source_service_id: str | None = None,
        persist: bool = True,
    ) -> GlobalRuntimeState:
        return self._apply_update_request(
            update_request,
            llm_state=llm_state,
            source=source,
            source_service_id=source_service_id,
            persist=persist,
        )

    def reset_to_env_defaults(
        self,
        *,
        source: str = "env",
        persist: bool = False,
    ) -> GlobalRuntimeState:
        provider_config = resolve_capability_provider_config(env=self._base_env)
        self._state = GlobalRuntimeState(
            provider_selection=ProviderSelection(
                provider=provider_config.provider,
                model=provider_config.model,
                endpoint=provider_config.endpoint,
                timeout_ms=provider_config.timeout_ms,
                retry_policy=provider_config.retry_policy,
            ),
            dev_mode=self._base_env.get("MIND_DEV_MODE", "").strip().lower() in _TRUE_ENV_VALUES,
            source=source,
            source_service_id=None,
        )
        self._sync_live_env(dict(self._base_env))
        if persist:
            self._persist_runtime_state()
        return self._state

    def runtime_payload(self) -> dict[str, Any]:
        self.bootstrap()
        state = self._state
        return {
            "scope": "process",
            "source": state.source,
            "provider": state.provider_selection.provider,
            "model": state.provider_selection.model,
            "endpoint": state.provider_selection.endpoint,
            "dev_mode": state.dev_mode,
            "source_service_id": state.source_service_id,
        }

    def preferences(self) -> Mapping[str, Any]:
        self.bootstrap()
        return self._preferences_for_principal(SYSTEM_RUNTIME_PRINCIPAL_ID)

    def _load_runtime_preferences(self) -> tuple[Mapping[str, Any], str]:
        preferences = self._preferences_for_principal(SYSTEM_RUNTIME_PRINCIPAL_ID)
        if preferences:
            return preferences, "persisted"
        legacy_preferences = self._preferences_for_principal(LEGACY_FRONTEND_RUNTIME_PRINCIPAL_ID)
        if not legacy_preferences:
            return {}, "env"
        self._persist_preferences(SYSTEM_RUNTIME_PRINCIPAL_ID, dict(legacy_preferences))
        return self._preferences_for_principal(SYSTEM_RUNTIME_PRINCIPAL_ID), "migrated"

    def _preferences_for_principal(self, principal_id: str) -> Mapping[str, Any]:
        principal_response = self._user_state_service.get_principal(
            AppRequest(
                request_id=f"runtime-principal-{principal_id}",
                input={"principal_id": principal_id},
            )
        )
        if principal_response.status is not AppStatus.OK or principal_response.result is None:
            return {}
        preferences = principal_response.result.get("preferences", {})
        return preferences if isinstance(preferences, Mapping) else {}

    def _persist_preferences(self, principal_id: str, preference_update: Mapping[str, Any]) -> None:
        self._user_state_service.resolve_principal(
            AppRequest(
                request_id=f"runtime-resolve-{principal_id}",
                input={"principal_id": principal_id},
            )
        )
        response = self._user_state_service.update_user_preferences(
            AppRequest(
                request_id=f"runtime-update-{principal_id}",
                input={
                    "principal_id": principal_id,
                    "preferences": dict(preference_update),
                },
            )
        )
        if response.status is not AppStatus.OK:
            raise RuntimeError("unable to persist global runtime state")

    def _persist_runtime_state(self) -> None:
        from mind.frontend.settings import dump_frontend_runtime_state

        self._persist_preferences(
            SYSTEM_RUNTIME_PRINCIPAL_ID,
            dump_frontend_runtime_state(
                {
                    "provider": self._state.provider_selection.provider,
                    "model": self._state.provider_selection.model,
                    "endpoint": self._state.provider_selection.endpoint,
                    "dev_mode": self._state.dev_mode,
                    "source": self._state.source,
                    "source_service_id": self._state.source_service_id,
                }
            ),
        )

    def _apply_update_request(
        self,
        update_request: Any,
        *,
        llm_state: Mapping[str, Any] | None,
        source: str,
        source_service_id: str | None,
        persist: bool,
    ) -> GlobalRuntimeState:
        from mind.frontend.settings import resolve_frontend_llm_runtime_endpoint

        next_request = update_request
        selection_input: dict[str, Any] = {}
        current_selection = self._state.provider_selection
        live_preferences = {"frontend_llm_state": llm_state} if llm_state is not None else None

        if getattr(next_request, "provider", None) is not None:
            requested_provider = str(next_request.provider)
            normalized_provider = self._normalize_provider_name(requested_provider)
            selection_input["provider"] = normalized_provider
            if getattr(next_request, "model", None) is not None:
                selection_input["model"] = (
                    "deterministic"
                    if selection_input["provider"] == "deterministic"
                    else next_request.model
                )
        elif getattr(next_request, "model", None) is not None:
            selection_input["provider"] = current_selection.provider
            selection_input["model"] = next_request.model
            selection_input["timeout_ms"] = current_selection.timeout_ms
            selection_input["retry_policy"] = current_selection.retry_policy
        if getattr(next_request, "endpoint", None) is not None and str(next_request.endpoint).strip():
            selection_input["endpoint"] = resolve_frontend_llm_runtime_endpoint(
                str(selection_input.get("provider") or current_selection.provider),
                str(next_request.endpoint).strip(),
            )

        if selection_input:
            live_env = self._compose_env(
                preferences=live_preferences,
                provider=selection_input.get("provider"),
                request_input=next_request.model_dump(mode="json"),
                dev_mode=(
                    bool(next_request.dev_mode)
                    if getattr(next_request, "dev_mode", None) is not None
                    else self._state.dev_mode
                ),
            )
            resolved_provider = resolve_capability_provider_config(
                selection=selection_input,
                env=live_env,
            )
            provider_selection = ProviderSelection(
                provider=resolved_provider.provider,
                model=resolved_provider.model,
                endpoint=resolved_provider.endpoint,
                timeout_ms=resolved_provider.timeout_ms,
                retry_policy=resolved_provider.retry_policy,
            )
        else:
            provider_selection = current_selection

        dev_mode = (
            bool(next_request.dev_mode)
            if getattr(next_request, "dev_mode", None) is not None
            else self._state.dev_mode
        )
        self._state = GlobalRuntimeState(
            provider_selection=provider_selection,
            dev_mode=dev_mode,
            source=source,
            source_service_id=source_service_id,
        )
        self._sync_live_env(
            self._compose_env(
                preferences=live_preferences,
                provider=self._state.provider_selection.provider,
                dev_mode=self._state.dev_mode,
            )
        )
        if persist:
            self._persist_runtime_state()
        return self._state

    def _compose_env(
        self,
        *,
        preferences: Mapping[str, Any] | None = None,
        provider: str | None = None,
        request_input: Mapping[str, Any] | None = None,
        dev_mode: bool | None = None,
    ) -> dict[str, str]:
        from mind.frontend.settings import (
            find_frontend_llm_service,
            frontend_llm_provider_catalog,
            load_frontend_llm_state,
            provider_secret_env,
            resolve_frontend_llm_runtime_endpoint,
        )

        active_env = dict(self._base_env)
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
        current_selection = self._state.provider_selection
        requested_provider = (
            str(request_payload.get("provider"))
            if request_payload.get("provider") is not None
            else (
                str(selected_service["protocol"])
                if selected_service is not None
                else provider or current_selection.provider
            )
        )
        next_provider = self._normalize_provider_name(requested_provider)
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
            elif next_provider == current_selection.provider and current_selection.endpoint is not None:
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
        if next_provider != "deterministic" and isinstance(api_key_override, str) and api_key_override:
            secret_env = provider_secret_env(next_provider)
            if secret_env is not None:
                active_env[secret_env] = api_key_override

        if next_provider == current_selection.provider:
            active_env["MIND_PROVIDER_TIMEOUT_MS"] = str(current_selection.timeout_ms)
            active_env["MIND_PROVIDER_RETRY_POLICY"] = current_selection.retry_policy
        else:
            active_env.pop("MIND_PROVIDER_TIMEOUT_MS", None)
            active_env.pop("MIND_PROVIDER_RETRY_POLICY", None)
        active_env["MIND_DEV_MODE"] = "true" if (self._state.dev_mode if dev_mode is None else dev_mode) else "false"
        return active_env

    def _normalize_provider_name(self, provider: str) -> str:
        return "deterministic" if provider in _BUILTIN_PROVIDERS else provider

    def _sync_live_env(self, active_env: Mapping[str, str]) -> None:
        self._env = dict(self._base_env)
        for key in _LIVE_PROVIDER_ENV_KEYS:
            if key in active_env:
                self._env[key] = str(active_env[key])
            else:
                self._env.pop(key, None)
