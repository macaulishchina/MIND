from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mind.capabilities import (
    CapabilityAdapterDescriptor,
    CapabilityInvocationTrace,
    CapabilityName,
    CapabilityProviderFamily,
    CapabilityRequest,
    CapabilityResponse,
    DeterministicCapabilityAdapter,
    assert_capability_gate,
    evaluate_capability_gate,
    write_capability_gate_report_json,
)


class _ProviderAdapter:
    def __init__(self, provider_family: CapabilityProviderFamily) -> None:
        self._provider_family = provider_family
        self._baseline = DeterministicCapabilityAdapter(clock=_fixed_clock)
        self.descriptor = CapabilityAdapterDescriptor(
            adapter_name=f"{provider_family.value}-test-adapter",
            provider_family=provider_family,
            model=f"{provider_family.value}-model",
            version="v1",
            api_style="test",
            supported_capabilities=list(CapabilityName),
        )

    def invoke(self, request: CapabilityRequest) -> CapabilityResponse:
        response = self._baseline.invoke(request)
        return response.model_copy(
            update={
                "trace": CapabilityInvocationTrace(
                    provider_family=self._provider_family,
                    model=f"{self._provider_family.value}-model",
                    endpoint=f"https://provider.example/{self._provider_family.value}",
                    version="v1",
                    started_at=_fixed_clock(),
                    completed_at=_fixed_clock(),
                    duration_ms=0,
                )
            }
        )


def test_phase_k_gate_fails_current_unconfigured_baseline() -> None:
    result = evaluate_capability_gate()

    assert result.k1_pass
    assert result.k4_pass
    assert result.k5_pass
    assert result.k6_pass
    assert not result.k2_pass
    assert not result.k3_pass
    assert not result.k7_pass
    assert not result.capability_gate_pass

    with pytest.raises(RuntimeError, match="K-2 failed"):
        assert_capability_gate(result)


def test_phase_k_gate_passes_with_all_provider_adapters() -> None:
    result = evaluate_capability_gate(
        adapters=[
            _ProviderAdapter(CapabilityProviderFamily.OPENAI),  # type: ignore[list-item]
            _ProviderAdapter(CapabilityProviderFamily.CLAUDE),  # type: ignore[list-item]
            _ProviderAdapter(CapabilityProviderFamily.GEMINI),  # type: ignore[list-item]
        ]
    )

    assert result.k1_pass
    assert result.k2_pass
    assert result.k3_pass
    assert result.k4_pass
    assert result.k5_pass
    assert result.k6_pass
    assert result.k7_pass
    assert result.capability_gate_pass
    assert_capability_gate(result)


def test_phase_k_gate_report_writes_json(tmp_path: Path) -> None:
    result = evaluate_capability_gate(
        adapters=[
            _ProviderAdapter(CapabilityProviderFamily.OPENAI),  # type: ignore[list-item]
            _ProviderAdapter(CapabilityProviderFamily.CLAUDE),  # type: ignore[list-item]
            _ProviderAdapter(CapabilityProviderFamily.GEMINI),  # type: ignore[list-item]
        ]
    )

    output_path = write_capability_gate_report_json(tmp_path / "phase_k_report.json", result)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "capability_gate_report_v1"
    assert payload["capability_gate_pass"] is True
    assert payload["k1_pass"] is True
    assert payload["k7_pass"] is True
    assert payload["compatibility_report"]["benchmark_pass_rate"] == 1.0


def _fixed_clock() -> datetime:
    return datetime(2026, 3, 11, 21, 0, tzinfo=UTC)
