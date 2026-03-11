from __future__ import annotations

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
)
from mind.cli import capability_compatibility_report_main, capability_gate_main


def _fixed_clock() -> datetime:
    return datetime(2026, 3, 11, 22, 0, tzinfo=UTC)


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


def test_capability_gate_main_prints_pass_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "mind.cli._build_live_capability_adapters",
        lambda requested_providers: [
            _ProviderAdapter(CapabilityProviderFamily.OPENAI),  # type: ignore[list-item]
            _ProviderAdapter(CapabilityProviderFamily.CLAUDE),  # type: ignore[list-item]
            _ProviderAdapter(CapabilityProviderFamily.GEMINI),  # type: ignore[list-item]
        ],
    )

    output_path = tmp_path / "phase_k_gate.json"
    exit_code = capability_gate_main(
        [
            "--output",
            str(output_path),
            "--live-provider",
            "openai",
            "--live-provider",
            "claude",
            "--live-provider",
            "gemini",
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
    output = capsys.readouterr().out
    assert "Phase K gate report" in output
    assert "live_providers=openai,claude,gemini" in output
    assert "K-7=PASS" in output
    assert "phase_k_gate=PASS" in output


def test_capability_compatibility_report_main_prints_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "mind.cli._build_live_capability_adapters",
        lambda requested_providers: [
            _ProviderAdapter(CapabilityProviderFamily.OPENAI),  # type: ignore[list-item]
        ],
    )

    output_path = tmp_path / "phase_k_provider_compatibility.json"
    exit_code = capability_compatibility_report_main(
        [
            "--output",
            str(output_path),
            "--live-provider",
            "openai",
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
    output = capsys.readouterr().out
    assert "Phase K provider compatibility report" in output
    assert "live_providers=openai" in output
    assert "benchmark_case_count=48" in output
    assert "provider_openai=" in output


def test_capability_gate_main_rejects_missing_live_provider_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "mind.cli.build_capability_adapters_from_environment",
        lambda provider_families=None: [],
    )

    with pytest.raises(SystemExit, match="Missing configured auth for live providers: openai"):
        capability_gate_main(["--live-provider", "openai"])
