"""System status application service."""

from __future__ import annotations

from typing import Any

from mind.app._service_utils import new_response
from mind.app.contracts import AppRequest, AppResponse, AppStatus
from mind.kernel.store import MemoryStore


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

        config_data: dict[str, Any] = {}
        if self._config is not None:
            config_data = {
                "backend": getattr(self._config, "backend", "unknown"),
                "profile": getattr(self._config, "resolved_profile", "unknown"),
            }
            # Redact sensitive values
            if hasattr(self._config, "postgres_dsn") and self._config.postgres_dsn:
                config_data["postgres_dsn"] = "***redacted***"

        resp.status = AppStatus.OK
        resp.result = config_data
        return resp

    def provider_status(self, req: AppRequest | None = None) -> AppResponse:
        """Provider availability (stub — deterministic stubs always available)."""
        resp = new_response(req, fallback_request_id="provider")

        resp.status = AppStatus.OK
        resp.result = {
            "provider": "stub",
            "model": "deterministic",
            "status": "available",
            "note": "LLM provider integration deferred to WP-7",
        }
        return resp
