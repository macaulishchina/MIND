"""User-state scenario fixtures for productized transports."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UserStateScenario:
    """One user-state scenario."""

    scenario_id: str
    tenant_id: str
    principal_id: str
    session_id: str
    summary: str


def build_user_state_scenarios_v1() -> tuple[UserStateScenario, ...]:
    """Return UserStateScenarioSet v1."""

    scenarios = tuple(
        UserStateScenario(
            scenario_id=f"user-state-{index:02d}",
            tenant_id=f"tenant-{(index % 3) + 1}",
            principal_id=f"principal-{index:02d}",
            session_id=f"session-{index:02d}",
            summary=f"user-state scenario {index:02d}",
        )
        for index in range(1, 31)
    )
    if len(scenarios) != 30:
        raise RuntimeError(f"UserStateScenarioSet v1 expected 30 scenarios, got {len(scenarios)}")
    return scenarios
