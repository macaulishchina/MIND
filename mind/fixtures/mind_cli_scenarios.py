"""MindCliScenarioSet v1 fixtures for the unified CLI rollout."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MindCliScenario:
    scenario_id: str
    command_family: str
    argv: tuple[str, ...]
    summary: str
    requires_runtime: bool


def build_mind_cli_scenario_set_v1() -> list[MindCliScenario]:
    """Return the frozen MindCliScenarioSet v1 coverage skeleton."""

    scenarios = [
        MindCliScenario(
            "help_top_level",
            "help",
            ("mind", "-h"),
            "Inspect the unified top-level help output.",
            False,
        ),
        MindCliScenario(
            "help_primitive",
            "help",
            ("mind", "primitive", "-h"),
            "Inspect primitive command-family help.",
            False,
        ),
        MindCliScenario(
            "help_access",
            "help",
            ("mind", "access", "-h"),
            "Inspect access command-family help.",
            False,
        ),
        MindCliScenario(
            "help_gate",
            "help",
            ("mind", "gate", "-h"),
            "Inspect gate command-family help.",
            False,
        ),
        MindCliScenario(
            "help_config",
            "help",
            ("mind", "config", "-h"),
            "Inspect config command-family help.",
            False,
        ),
        MindCliScenario(
            "primitive_write_raw",
            "primitive",
            ("mind", "primitive", "write-raw"),
            "Write a raw record through the unified primitive entry point.",
            True,
        ),
        MindCliScenario(
            "primitive_read",
            "primitive",
            ("mind", "primitive", "read"),
            "Read an object by id through the unified primitive entry point.",
            True,
        ),
        MindCliScenario(
            "primitive_retrieve",
            "primitive",
            ("mind", "primitive", "retrieve"),
            "Retrieve memory candidates through the unified primitive entry point.",
            True,
        ),
        MindCliScenario(
            "primitive_summarize",
            "primitive",
            ("mind", "primitive", "summarize"),
            "Generate a summary through the unified primitive entry point.",
            True,
        ),
        MindCliScenario(
            "access_run_flash",
            "access",
            ("mind", "access", "run", "--mode", "flash"),
            "Run the shallow flash access mode.",
            True,
        ),
        MindCliScenario(
            "access_run_auto",
            "access",
            ("mind", "access", "run", "--mode", "auto"),
            "Run the auto access scheduler.",
            True,
        ),
        MindCliScenario(
            "access_benchmark",
            "access",
            ("mind", "access", "benchmark"),
            "Run the AccessDepthBench comparison entry point.",
            True,
        ),
        MindCliScenario(
            "offline_worker",
            "offline",
            ("mind", "offline", "worker"),
            "Run one offline worker batch.",
            True,
        ),
        MindCliScenario(
            "offline_replay",
            "offline",
            ("mind", "offline", "replay"),
            "Inspect replay target selection.",
            True,
        ),
        MindCliScenario(
            "offline_reflect_episode",
            "offline",
            ("mind", "offline", "reflect-episode"),
            "Trigger a single reflect-episode maintenance flow.",
            True,
        ),
        MindCliScenario(
            "governance_plan_conceal",
            "governance",
            ("mind", "governance", "plan-conceal"),
            "Plan a conceal operation.",
            True,
        ),
        MindCliScenario(
            "governance_preview",
            "governance",
            ("mind", "governance", "preview"),
            "Preview a governance operation.",
            True,
        ),
        MindCliScenario(
            "governance_execute_conceal",
            "governance",
            ("mind", "governance", "execute-conceal"),
            "Execute a conceal governance operation.",
            True,
        ),
        MindCliScenario(
            "gate_kernel",
            "gate",
            ("mind", "gate", "phase-b"),
            "Run the kernel gate from the unified gate family.",
            True,
        ),
        MindCliScenario(
            "gate_access",
            "gate",
            ("mind", "gate", "phase-i"),
            "Run the access gate from the unified gate family.",
            True,
        ),
        MindCliScenario(
            "gate_postgres_regression",
            "gate",
            ("mind", "gate", "postgres-regression"),
            "Run PostgreSQL regression from the unified gate family.",
            True,
        ),
        MindCliScenario(
            "report_benchmark_ci",
            "report",
            ("mind", "report", "phase-f-ci"),
            "Run the repeated benchmark CI report entry point.",
            True,
        ),
        MindCliScenario(
            "report_acceptance_h",
            "report",
            ("mind", "report", "acceptance", "--phase", "h"),
            "Inspect the frozen governance acceptance report path.",
            False,
        ),
        MindCliScenario(
            "demo_ingest_read",
            "demo",
            ("mind", "demo", "ingest-read"),
            "Walk through ingesting and reading memory objects.",
            True,
        ),
        MindCliScenario(
            "demo_access_run",
            "demo",
            ("mind", "demo", "access-run"),
            "Walk through a runtime access mode run.",
            True,
        ),
        MindCliScenario(
            "config_show",
            "config",
            ("mind", "config", "show"),
            "Inspect the active CLI profile and backend configuration.",
            False,
        ),
    ]

    required_families = {
        "help",
        "primitive",
        "access",
        "offline",
        "governance",
        "gate",
        "report",
        "demo",
        "config",
    }
    scenario_families = {scenario.command_family for scenario in scenarios}
    missing_families = required_families - scenario_families
    if missing_families:
        missing = ", ".join(sorted(missing_families))
        raise RuntimeError(f"MindCliScenarioSet v1 missing families: {missing}")
    if len(scenarios) != 26:
        raise RuntimeError(f"MindCliScenarioSet v1 expected 26 scenarios, got {len(scenarios)}")
    return scenarios
