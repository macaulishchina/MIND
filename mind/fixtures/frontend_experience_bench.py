"""Frozen fixture manifest for Phase M frontend experience coverage."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FrontendExperienceScenario:
    """One frontend-facing experience scenario frozen for Phase M."""

    scenario_id: str
    category: str
    entrypoint: str
    viewport: str
    requires_dev_mode: bool
    summary: str


def build_frontend_experience_bench_v1() -> list[FrontendExperienceScenario]:
    """Return the frozen FrontendExperienceBench v1 manifest."""

    scenarios = [
        FrontendExperienceScenario(
            "ingest_basic_desktop",
            "experience",
            "ingest",
            "desktop",
            False,
            "Desktop ingest flow stores one memory and returns the created object id.",
        ),
        FrontendExperienceScenario(
            "ingest_basic_mobile",
            "experience",
            "ingest",
            "mobile",
            False,
            "Mobile ingest flow preserves the same request/response contract.",
        ),
        FrontendExperienceScenario(
            "retrieve_keyword_desktop",
            "experience",
            "retrieve",
            "desktop",
            False,
            "Desktop retrieve flow returns keyword-ranked memory candidates.",
        ),
        FrontendExperienceScenario(
            "retrieve_episode_mobile",
            "experience",
            "retrieve",
            "mobile",
            False,
            "Mobile retrieve flow supports filtered recall within one episode.",
        ),
        FrontendExperienceScenario(
            "access_run_auto_desktop",
            "experience",
            "access",
            "desktop",
            False,
            "Desktop ask/access flow runs auto depth and returns "
            "answer details plus trace-backed context.",
        ),
        FrontendExperienceScenario(
            "access_explain_mobile",
            "experience",
            "access",
            "mobile",
            False,
            "Mobile access explain flow surfaces resolved depth, "
            "selected evidence, and answer support details.",
        ),
        FrontendExperienceScenario(
            "offline_reflect_submit_desktop",
            "experience",
            "offline",
            "desktop",
            False,
            "Desktop offline flow submits a reflect_episode job through the product boundary.",
        ),
        FrontendExperienceScenario(
            "offline_promote_submit_mobile",
            "experience",
            "offline",
            "mobile",
            False,
            "Mobile offline flow submits a promote_schema job without changing semantics.",
        ),
        FrontendExperienceScenario(
            "gate_demo_catalog_desktop",
            "experience",
            "gate_demo",
            "desktop",
            False,
            "Desktop gate/demo view exposes benchmark and gate entry summaries.",
        ),
        FrontendExperienceScenario(
            "gate_demo_catalog_mobile",
            "experience",
            "gate_demo",
            "mobile",
            False,
            "Mobile gate/demo view stays navigable with the same summary contract.",
        ),
        FrontendExperienceScenario(
            "config_backend_profile_desktop",
            "config",
            "config_backend",
            "desktop",
            False,
            "Desktop config view shows the current runtime environment as read-only context.",
        ),
        FrontendExperienceScenario(
            "config_backend_profile_mobile",
            "config",
            "config_backend",
            "mobile",
            False,
            "Mobile config view keeps the runtime environment "
            "visible without exposing an edit path.",
        ),
        FrontendExperienceScenario(
            "config_provider_model_desktop",
            "config",
            "config_provider",
            "desktop",
            False,
            "Desktop config view can switch answer mode immediately "
            "and still expose the LLM detail entrypoint.",
        ),
        FrontendExperienceScenario(
            "config_dev_mode_toggle_desktop",
            "config",
            "config_dev_mode",
            "desktop",
            False,
            "Desktop config view exposes dev-mode as an explicit switch with immediate effect.",
        ),
        FrontendExperienceScenario(
            "config_llm_placeholder_mobile",
            "config",
            "config_llm",
            "mobile",
            False,
            "Mobile config flow exposes a dedicated LLM configuration placeholder entrypoint.",
        ),
        FrontendExperienceScenario(
            "debug_timeline_desktop",
            "debug",
            "debug_timeline",
            "desktop",
            True,
            "Desktop debug timeline visualizes ordered internal events for one run.",
        ),
        FrontendExperienceScenario(
            "debug_timeline_mobile",
            "debug",
            "debug_timeline",
            "mobile",
            True,
            "Mobile debug timeline preserves causal ordering and readable summaries.",
        ),
        FrontendExperienceScenario(
            "debug_object_delta_desktop",
            "debug",
            "debug_object_delta",
            "desktop",
            True,
            "Desktop debug view shows before/after/delta snapshots for mutated objects.",
        ),
        FrontendExperienceScenario(
            "debug_context_evidence_desktop",
            "debug",
            "debug_context",
            "desktop",
            True,
            "Desktop debug view shows context selection, evidence support, and access reasoning.",
        ),
        FrontendExperienceScenario(
            "debug_dev_mode_guard",
            "debug",
            "debug_guard",
            "shared",
            True,
            "Debug routes remain unavailable outside dev-mode and do not leak internal data.",
        ),
    ]

    expected_categories = {"experience", "config", "debug"}
    expected_entrypoints = {
        "ingest",
        "retrieve",
        "access",
        "offline",
        "gate_demo",
        "config_backend",
        "config_provider",
        "config_dev_mode",
        "config_llm",
        "debug_timeline",
        "debug_object_delta",
        "debug_context",
        "debug_guard",
    }
    actual_categories = {scenario.category for scenario in scenarios}
    actual_entrypoints = {scenario.entrypoint for scenario in scenarios}
    if actual_categories != expected_categories:
        missing = sorted(expected_categories - actual_categories)
        extra = sorted(actual_categories - expected_categories)
        raise RuntimeError(
            f"FrontendExperienceBench v1 category mismatch: missing={missing}, extra={extra}"
        )
    if actual_entrypoints != expected_entrypoints:
        missing = sorted(expected_entrypoints - actual_entrypoints)
        extra = sorted(actual_entrypoints - expected_entrypoints)
        raise RuntimeError(
            f"FrontendExperienceBench v1 entrypoint mismatch: missing={missing}, extra={extra}"
        )
    if len(scenarios) != 20:
        raise RuntimeError(
            f"FrontendExperienceBench v1 expected 20 scenarios, got {len(scenarios)}"
        )
    return scenarios
