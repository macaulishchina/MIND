"""Product CLI benchmark fixture set."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProductCliScenario:
    """One product CLI experience scenario."""

    scenario_id: str
    command_family: str
    argv: tuple[str, ...]
    summary: str


def build_product_cli_bench_v1() -> tuple[ProductCliScenario, ...]:
    """Return ProductCliExperienceBench v1."""

    scenarios = (
        ProductCliScenario("help_top", "help", ("mind", "-h"), "Top-level help."),
        ProductCliScenario("help_remember", "help", ("mind", "remember", "-h"), "remember help."),
        ProductCliScenario("help_recall", "help", ("mind", "recall", "-h"), "recall help."),
        ProductCliScenario("help_ask", "help", ("mind", "ask", "-h"), "ask help."),
        ProductCliScenario("help_history", "help", ("mind", "history", "-h"), "history help."),
        ProductCliScenario("help_session", "help", ("mind", "session", "-h"), "session help."),
        ProductCliScenario("help_status", "help", ("mind", "status", "-h"), "status help."),
        ProductCliScenario("help_config", "help", ("mind", "config", "-h"), "config help."),
        ProductCliScenario(
            "help_session_open",
            "session",
            ("mind", "session", "open", "-h"),
            "session open help.",
        ),
        ProductCliScenario(
            "help_session_list",
            "session",
            ("mind", "session", "list", "-h"),
            "session list help.",
        ),
        ProductCliScenario(
            "help_session_show",
            "session",
            ("mind", "session", "show", "-h"),
            "session show help.",
        ),
        ProductCliScenario(
            "remember_basic",
            "remember",
            ("mind", "remember", "hello", "--episode-id", "ep-1"),
            "Store a basic memory.",
        ),
        ProductCliScenario(
            "remember_with_session",
            "remember",
            (
                "mind",
                "remember",
                "hello again",
                "--episode-id",
                "ep-1",
                "--session-id",
                "session-1",
            ),
            "Store with an explicit session.",
        ),
        ProductCliScenario(
            "recall_keyword",
            "recall",
            ("mind", "recall", "hello"),
            "Recall with keyword mode.",
        ),
        ProductCliScenario(
            "recall_custom_budget",
            "recall",
            ("mind", "recall", "hello", "--max-candidates", "5"),
            "Recall with lower candidate budget.",
        ),
        ProductCliScenario(
            "ask_auto",
            "ask",
            ("mind", "ask", "seed"),
            "Ask with auto mode.",
        ),
        ProductCliScenario(
            "ask_flash",
            "ask",
            ("mind", "ask", "seed", "--mode", "flash"),
            "Ask with flash mode.",
        ),
        ProductCliScenario(
            "ask_with_episode",
            "ask",
            ("mind", "ask", "seed", "--episode-id", "ep-1"),
            "Ask scoped to one episode.",
        ),
        ProductCliScenario(
            "history_default",
            "history",
            ("mind", "history"),
            "List recent history.",
        ),
        ProductCliScenario(
            "history_limit",
            "history",
            ("mind", "history", "--limit", "5"),
            "List limited history.",
        ),
        ProductCliScenario(
            "history_offset",
            "history",
            ("mind", "history", "--limit", "5", "--offset", "2"),
            "List paginated history.",
        ),
        ProductCliScenario(
            "history_episode",
            "history",
            ("mind", "history", "--episode-id", "ep-1"),
            "List history by episode.",
        ),
        ProductCliScenario(
            "session_open",
            "session",
            (
                "mind",
                "session",
                "open",
                "--principal-id",
                "cli-user",
                "--session-id",
                "session-1",
            ),
            "Open one session.",
        ),
        ProductCliScenario(
            "session_open_with_conversation",
            "session",
            (
                "mind",
                "session",
                "open",
                "--principal-id",
                "cli-user",
                "--session-id",
                "session-2",
                "--conversation-id",
                "conv-2",
            ),
            "Open session with conversation id.",
        ),
        ProductCliScenario(
            "session_list",
            "session",
            ("mind", "session", "list"),
            "List sessions.",
        ),
        ProductCliScenario(
            "session_list_principal",
            "session",
            ("mind", "session", "list", "--principal-id", "cli-user"),
            "List sessions for one principal.",
        ),
        ProductCliScenario(
            "session_show",
            "session",
            ("mind", "session", "show", "session-1"),
            "Show session details.",
        ),
        ProductCliScenario(
            "status_basic",
            "status",
            ("mind", "status"),
            "Show health and readiness.",
        ),
        ProductCliScenario(
            "config_basic",
            "config",
            ("mind", "config"),
            "Show resolved config.",
        ),
        ProductCliScenario(
            "config_local_explicit",
            "config",
            ("mind", "--local", "config"),
            "Show local config explicitly.",
        ),
    )

    if len(scenarios) != 30:
        raise RuntimeError(
            f"ProductCliExperienceBench v1 expected 30 scenarios, got {len(scenarios)}"
        )
    return scenarios
