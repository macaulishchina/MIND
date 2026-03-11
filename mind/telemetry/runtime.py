"""Runtime helpers for Phase L development telemetry."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from os import environ
from pathlib import Path
from typing import Protocol

from .contracts import TelemetryEvent

DEV_TELEMETRY_PATH_ENV = "MIND_DEV_TELEMETRY_PATH"


class TelemetryRecorder(Protocol):
    """Minimal recorder contract used by instrumented runtimes."""

    def record(self, event: TelemetryEvent) -> None: ...


class InMemoryTelemetryRecorder:
    """Simple in-memory recorder for tests and local development."""

    def __init__(self) -> None:
        self._events: list[TelemetryEvent] = []

    def record(self, event: TelemetryEvent) -> None:
        self._events.append(event)

    def iter_events(self) -> Sequence[TelemetryEvent]:
        return tuple(self._events)

    def clear(self) -> None:
        self._events.clear()


class JsonlTelemetryRecorder:
    """Append-only JSONL telemetry sink for dev-mode persistence."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def record(self, event: TelemetryEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")

    def iter_events(self) -> Sequence[TelemetryEvent]:
        if not self.path.exists():
            return ()
        events: list[TelemetryEvent] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    events.append(TelemetryEvent.model_validate_json(line))
        return tuple(events)

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


class CompositeTelemetryRecorder:
    """Fan out one telemetry event to multiple sinks."""

    def __init__(self, recorders: Sequence[TelemetryRecorder]) -> None:
        self._recorders = tuple(recorders)

    def record(self, event: TelemetryEvent) -> None:
        for recorder in self._recorders:
            recorder.record(event)


def resolve_dev_telemetry_path(
    *,
    telemetry_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path | None:
    """Resolve the optional dev telemetry persistence path."""

    if telemetry_path is not None:
        return Path(telemetry_path)
    active_env = env or environ
    configured = active_env.get(DEV_TELEMETRY_PATH_ENV)
    if configured:
        return Path(configured)
    return None


def build_dev_telemetry_recorder(
    *,
    telemetry_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> JsonlTelemetryRecorder | None:
    """Build the default dev telemetry recorder when persistence is configured."""

    resolved = resolve_dev_telemetry_path(telemetry_path=telemetry_path, env=env)
    if resolved is None:
        return None
    return JsonlTelemetryRecorder(resolved)
