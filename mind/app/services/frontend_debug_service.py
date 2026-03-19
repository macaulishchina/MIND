"""Frontend debug application service."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from os import environ
from pathlib import Path
from typing import Any, Protocol

from mind.telemetry import JsonlTelemetryRecorder, TelemetryEvent, resolve_dev_telemetry_path

_TRUE_ENV_VALUES = frozenset({"1", "true", "yes", "on"})


class _TelemetryEventSource(Protocol):
    def iter_events(self) -> Sequence[TelemetryEvent]: ...


class FrontendDebugAppService:
    """Resolve and query telemetry-backed debug timelines for frontend consumers."""

    def __init__(
        self,
        *,
        telemetry_source: _TelemetryEventSource | None = None,
        telemetry_path: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        dev_mode_resolver: Any = None,
    ) -> None:
        self._telemetry_source = telemetry_source
        self._telemetry_path = resolve_dev_telemetry_path(telemetry_path=telemetry_path, env=env)
        self._env = env
        self._dev_mode_resolver = dev_mode_resolver

    def query_timeline(
        self,
        query: Any,
        *,
        dev_mode: bool | None = None,
    ) -> Any:
        """Return a frontend-facing debug timeline."""

        from mind.app.frontend_debug import build_frontend_debug_timeline

        return build_frontend_debug_timeline(
            self._iter_events(),
            query,
            dev_mode=self._resolve_dev_mode(dev_mode),
        )

    def load_workspace(
        self,
        *,
        dev_mode: bool | None = None,
    ) -> Any:
        """Return frontend-facing filter metadata for the debug workspace."""

        from mind.app.frontend_debug_workspace import build_frontend_debug_workspace

        return build_frontend_debug_workspace(
            self._iter_events(),
            dev_mode=self._resolve_dev_mode(dev_mode),
        )

    def _iter_events(self) -> Sequence[TelemetryEvent]:
        if self._telemetry_source is not None:
            return tuple(self._telemetry_source.iter_events())
        if self._telemetry_path is None:
            return ()
        return JsonlTelemetryRecorder(self._telemetry_path).iter_events()

    def _resolve_dev_mode(self, override: bool | None) -> bool:
        if override is not None:
            return override
        if self._dev_mode_resolver is not None:
            return bool(self._dev_mode_resolver())
        active_env = self._env or environ
        return active_env.get("MIND_DEV_MODE", "").strip().lower() in _TRUE_ENV_VALUES
