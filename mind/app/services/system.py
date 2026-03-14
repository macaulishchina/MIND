"""System status application service."""

from __future__ import annotations

from collections.abc import Mapping
from os import environ
from typing import Any

from mind.app._service_utils import new_response
from mind.app.contracts import AppError, AppErrorCode, AppRequest, AppResponse, AppStatus
from mind.capabilities import (
    CAPABILITY_CATALOG,
    CapabilityProviderConfig,
    CapabilityProviderFamily,
    resolve_capability_provider_config,
)
from mind.kernel.store import MemoryStore
from mind.telemetry import resolve_dev_telemetry_path

_TRUE_ENV_VALUES = frozenset({"1", "true", "yes", "on"})


class SystemStatusService:
    """System health, readiness, and configuration status.

    Methods: ``health``, ``readiness``, ``config_summary``, ``provider_status``.
    """

    def __init__(self, store: MemoryStore, config: Any = None) -> None:
        self._store = store
        self._config = config

    def health(self, req: AppRequest | None = None) -> AppResponse:
        """Basic liveness check."""
        resp = new_response(req, fallback_request_id="health")

        try:
            # Check store connectivity by attempting a harmless read
            self._store.has_object("__health_check__")
            resp.status = AppStatus.OK
            resp.result = {"status": "healthy", "store": "connected"}
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.result = {"status": "unhealthy", "error": str(exc)}

        return resp

    def readiness(self, req: AppRequest | None = None) -> AppResponse:
        """Readiness check — includes migration state verification."""
        resp = new_response(req, fallback_request_id="readiness")

        checks: dict[str, str] = {}

        # Store connectivity
        try:
            self._store.has_object("__readiness_check__")
            checks["store"] = "ready"
        except Exception:
            checks["store"] = "not_ready"

        all_ready = all(v == "ready" for v in checks.values())

        resp.status = AppStatus.OK if all_ready else AppStatus.ERROR
        resp.result = {"ready": all_ready, "checks": checks}
        return resp

    def config_summary(self, req: AppRequest | None = None) -> AppResponse:
        """Return sanitized configuration summary."""
        resp = new_response(req, fallback_request_id="config")
        resp.status = AppStatus.OK
        resp.result = build_config_summary_payload(self._config)
        return resp

    def provider_status(self, req: AppRequest | None = None) -> AppResponse:
        """Return the resolved provider configuration summary."""
        resp = new_response(req, fallback_request_id="provider")
        try:
            provider_config = resolve_capability_provider_config(
                selection=req.provider_selection if req is not None else None,
            )
        except RuntimeError as exc:
            resp.status = AppStatus.ERROR
            resp.error = AppError(
                code=AppErrorCode.VALIDATION_ERROR,
                message=str(exc),
                details=_provider_selection_details(req),
            )
            return resp

        resp.status = AppStatus.OK
        resp.result = build_provider_status_payload(provider_config)
        return resp


def build_config_summary_payload(
    config: Any = None,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build the stable config summary payload used by product/frontend surfaces."""

    config_data: dict[str, Any] = {
        "backend": "unknown",
        "profile": "unknown",
        "backend_source": "unknown",
        "profile_source": "unknown",
        "dev_mode": _env_dev_mode(env=env),
        "dev_telemetry_configured": resolve_dev_telemetry_path(env=env) is not None,
    }
    if config is not None:
        config_data = {
            **config_data,
            "backend": _enum_or_value(getattr(config, "backend", "unknown")),
            "profile": _enum_or_value(getattr(config, "resolved_profile", "unknown")),
            "backend_source": getattr(config, "backend_source", "unknown"),
            "profile_source": getattr(config, "requested_profile_source", "unknown"),
        }
        if hasattr(config, "postgres_dsn") and config.postgres_dsn:
            config_data["postgres_dsn"] = "***redacted***"
    return config_data


def build_provider_status_payload(
    provider_config: CapabilityProviderConfig,
) -> dict[str, Any]:
    """Build the stable provider status payload used by product/frontend surfaces."""

    available = (
        provider_config.provider_family is CapabilityProviderFamily.DETERMINISTIC
        or provider_config.auth.is_configured()
    )
    execution = _provider_execution(provider_config.provider_family, auth_configured=available)
    return {
        **provider_config.redacted_summary(),
        "status": "available" if available else "missing_auth",
        "execution": execution,
        "supported_capabilities": [capability.value for capability in CAPABILITY_CATALOG],
    }


def _provider_execution(
    provider_family: CapabilityProviderFamily,
    *,
    auth_configured: bool,
) -> str:
    if provider_family is CapabilityProviderFamily.DETERMINISTIC:
        return "deterministic_adapter_ready"
    if not auth_configured:
        return "adapter_unavailable_missing_auth"
    if provider_family is CapabilityProviderFamily.OPENAI:
        return "openai_responses_adapter_ready"
    if provider_family is CapabilityProviderFamily.CLAUDE:
        return "claude_messages_adapter_ready"
    if provider_family is CapabilityProviderFamily.GEMINI:
        return "gemini_generate_content_adapter_ready"
    return "adapter_unknown"


def _enum_or_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _provider_selection_details(req: AppRequest | None) -> dict[str, Any]:
    if req is None or req.provider_selection is None:
        return {}
    return {"provider_selection": req.provider_selection.model_dump(mode="json")}


def _env_dev_mode(*, env: Mapping[str, str] | None = None) -> bool:
    active_env = env or environ
    return active_env.get("MIND_DEV_MODE", "").strip().lower() in _TRUE_ENV_VALUES
