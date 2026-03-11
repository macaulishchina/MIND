from __future__ import annotations

from mind.fixtures import build_internal_telemetry_bench_v1
from mind.telemetry import TelemetryEventKind, TelemetryScope


def test_internal_telemetry_bench_v1_is_frozen_and_complete() -> None:
    scenarios = build_internal_telemetry_bench_v1()

    assert len(scenarios) == 30
    assert {scenario.scope for scenario in scenarios} == {
        TelemetryScope.PRIMITIVE,
        TelemetryScope.RETRIEVAL,
        TelemetryScope.WORKSPACE,
        TelemetryScope.ACCESS,
        TelemetryScope.OFFLINE,
        TelemetryScope.GOVERNANCE,
        TelemetryScope.OBJECT_DELTA,
    }
    assert scenarios[0].scenario_id == "primitive_entry"
    assert scenarios[-1].scenario_id == "timeline_replay_anchor"


def test_internal_telemetry_bench_v1_has_state_delta_coverage() -> None:
    scenarios = build_internal_telemetry_bench_v1()

    state_delta_scenarios = [
        scenario for scenario in scenarios if scenario.kind is TelemetryEventKind.STATE_DELTA
    ]
    assert len(state_delta_scenarios) >= 8
    assert all(scenario.requires_state_delta for scenario in state_delta_scenarios)
