"""Adapter bridging CapabilityService to the primitives-layer CapabilityPort."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from .config import CapabilityProviderConfig, resolve_capability_provider_config
from .contracts import ReflectRequest, SummarizeRequest
from .service import CapabilityService


class CapabilityPortAdapter:
    """Satisfies ``primitives.contracts.CapabilityPort`` protocol."""

    def __init__(
        self,
        *,
        service: CapabilityService | None = None,
        clock: Callable[[], datetime] | None = None,
        provider_config: CapabilityProviderConfig | None = None,
    ) -> None:
        if service is not None:
            self._service = service
        else:
            self._service = CapabilityService(
                clock=clock,
                provider_config=provider_config,
            )

    def summarize_text(
        self,
        *,
        request_id: str,
        source_text: str,
        source_refs: list[str],
        instruction: str | None = None,
        provider_config: Any = None,
    ) -> str:
        return self._service.summarize(
            SummarizeRequest(
                request_id=request_id,
                source_text=source_text,
                source_refs=source_refs,
                instruction=instruction,
            ),
            provider_config=provider_config,
        ).summary_text

    def reflect_text(
        self,
        *,
        request_id: str,
        focus: str | dict[str, Any],
        evidence_text: str,
        episode_id: str | None = None,
        outcome_hint: str | None = None,
        evidence_refs: list[str] | None = None,
        provider_config: Any = None,
    ) -> str:
        return self._service.reflect(
            ReflectRequest(
                request_id=request_id,
                focus=focus,
                evidence_text=evidence_text,
                episode_id=episode_id,
                outcome_hint=outcome_hint,
                evidence_refs=evidence_refs or [],
            ),
            provider_config=provider_config,
        ).reflection_text

    def resolve_provider_config(
        self,
        *,
        selection: Any = None,
        env: Mapping[str, str] | None = None,
    ) -> Any:
        return resolve_capability_provider_config(selection=selection, env=env)
