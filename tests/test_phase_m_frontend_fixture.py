from __future__ import annotations

from mind.fixtures import build_frontend_experience_bench_v1


def test_frontend_experience_bench_v1_is_frozen_and_complete() -> None:
    scenarios = build_frontend_experience_bench_v1()

    assert len(scenarios) == 20
    assert {scenario.category for scenario in scenarios} == {"experience", "config", "debug"}
    assert scenarios[0].scenario_id == "ingest_basic_desktop"
    assert scenarios[-1].scenario_id == "debug_dev_mode_guard"


def test_frontend_experience_bench_v1_covers_phase_m_required_entrypoints() -> None:
    scenarios = build_frontend_experience_bench_v1()

    experience_entrypoints = {
        scenario.entrypoint
        for scenario in scenarios
        if scenario.category == "experience"
    }
    assert experience_entrypoints == {
        "ingest",
        "retrieve",
        "access",
        "offline",
        "gate_demo",
    }

    config_entrypoints = {
        scenario.entrypoint
        for scenario in scenarios
        if scenario.category == "config"
    }
    assert config_entrypoints == {
        "config_backend",
        "config_provider",
        "config_dev_mode",
        "config_restore",
    }


def test_frontend_experience_bench_v1_freezes_debug_and_viewport_constraints() -> None:
    scenarios = build_frontend_experience_bench_v1()

    debug_scenarios = [scenario for scenario in scenarios if scenario.category == "debug"]
    assert len(debug_scenarios) == 5
    assert all(scenario.requires_dev_mode for scenario in debug_scenarios)

    viewports = {scenario.viewport for scenario in scenarios}
    assert viewports == {"desktop", "mobile", "shared"}
    assert sum(scenario.viewport == "mobile" for scenario in scenarios) >= 6
