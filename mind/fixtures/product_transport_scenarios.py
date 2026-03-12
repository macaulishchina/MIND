"""Product transport scenario fixtures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProductTransportScenario:
    """A single transport-level scenario."""

    name: str
    method: str
    path: str
    expected_http_status: int
    expected_app_status: str
    json_body: dict[str, Any] | None = None
    params: Any = None
    headers: dict[str, str] | None = None
    required_json_paths: tuple[str, ...] = ()
    required_nonempty_json_paths: tuple[str, ...] = ()
    expected_json_values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProductTransportConsistencyScenario:
    """One frozen semantic scenario shared across product transports."""

    scenario_id: str
    command_family: str
    summary: str
    rest_method: str
    rest_path: str
    rest_json_body: dict[str, Any] | None = None
    mcp_tool_name: str | None = None
    mcp_args: dict[str, Any] = field(default_factory=dict)
    cli_argv: tuple[str, ...] | None = None


def build_product_transport_scenarios_v1(
    *,
    memory_id: str,
    second_memory_id: str,
    operation_id: str,
    pending_job_id: str,
    cancel_job_id: str,
    session_id: str,
    principal_id: str,
) -> tuple[ProductTransportScenario, ...]:
    """Return the v1 transport scenario set for REST transport contract verification."""

    return (
        ProductTransportScenario(
            name="system_health_ok",
            method="GET",
            path="/v1/system/health",
            expected_http_status=200,
            expected_app_status="ok",
        ),
        ProductTransportScenario(
            name="system_readiness_ok",
            method="GET",
            path="/v1/system/readiness",
            expected_http_status=200,
            expected_app_status="ok",
        ),
        ProductTransportScenario(
            name="system_config_ok",
            method="GET",
            path="/v1/system/config",
            expected_http_status=200,
            expected_app_status="ok",
            required_json_paths=("result.backend", "result.profile", "request_id"),
        ),
        ProductTransportScenario(
            name="frontend_catalog_ok",
            method="GET",
            path="/v1/frontend/catalog",
            expected_http_status=200,
            expected_app_status="ok",
            expected_json_values={"result.bench_version": "FrontendExperienceBench v1"},
        ),
        ProductTransportScenario(
            name="frontend_gate_demo_ok",
            method="GET",
            path="/v1/frontend/gate-demo",
            expected_http_status=200,
            expected_app_status="ok",
            expected_json_values={"result.page_version": "FrontendGateDemoPage v1"},
            required_nonempty_json_paths=("result.entries",),
        ),
        ProductTransportScenario(
            name="frontend_settings_ok",
            method="GET",
            path="/v1/frontend/settings",
            expected_http_status=200,
            expected_app_status="ok",
            required_json_paths=("result.runtime.backend", "result.provider.provider"),
        ),
        ProductTransportScenario(
            name="user_get_ok",
            method="GET",
            path=f"/v1/users/{principal_id}",
            expected_http_status=200,
            expected_app_status="ok",
        ),
        ProductTransportScenario(
            name="user_defaults_ok",
            method="GET",
            path=f"/v1/users/{principal_id}/defaults",
            expected_http_status=200,
            expected_app_status="ok",
        ),
        ProductTransportScenario(
            name="session_get_ok",
            method="GET",
            path=f"/v1/sessions/{session_id}",
            expected_http_status=200,
            expected_app_status="ok",
        ),
        ProductTransportScenario(
            name="memories_list_all",
            method="GET",
            path="/v1/memories",
            expected_http_status=200,
            expected_app_status="ok",
        ),
        ProductTransportScenario(
            name="memories_list_limit",
            method="GET",
            path="/v1/memories",
            expected_http_status=200,
            expected_app_status="ok",
            params={"limit": 2},
        ),
        ProductTransportScenario(
            name="memories_list_offset",
            method="GET",
            path="/v1/memories",
            expected_http_status=200,
            expected_app_status="ok",
            params={"limit": 2, "offset": 1},
        ),
        ProductTransportScenario(
            name="memories_list_episode",
            method="GET",
            path="/v1/memories",
            expected_http_status=200,
            expected_app_status="ok",
            params={"episode_id": "rest-ep-1"},
        ),
        ProductTransportScenario(
            name="memory_get_first",
            method="GET",
            path=f"/v1/memories/{memory_id}",
            expected_http_status=200,
            expected_app_status="ok",
        ),
        ProductTransportScenario(
            name="memory_get_second",
            method="GET",
            path=f"/v1/memories/{second_memory_id}",
            expected_http_status=200,
            expected_app_status="ok",
        ),
        ProductTransportScenario(
            name="memory_get_missing",
            method="GET",
            path="/v1/memories/missing-memory",
            expected_http_status=404,
            expected_app_status="not_found",
        ),
        ProductTransportScenario(
            name="memory_search_alpha",
            method="POST",
            path="/v1/memories:search",
            expected_http_status=200,
            expected_app_status="ok",
            json_body={"query": "alpha", "max_candidates": 5},
        ),
        ProductTransportScenario(
            name="memory_search_beta_limited",
            method="POST",
            path="/v1/memories:search",
            expected_http_status=200,
            expected_app_status="ok",
            json_body={"query": "beta", "max_candidates": 1},
        ),
        ProductTransportScenario(
            name="memory_recall_alpha",
            method="POST",
            path="/v1/memories:recall",
            expected_http_status=200,
            expected_app_status="ok",
            json_body={"query": "alpha", "query_modes": ["keyword"]},
        ),
        ProductTransportScenario(
            name="memory_recall_episode",
            method="POST",
            path="/v1/memories:recall",
            expected_http_status=200,
            expected_app_status="ok",
            json_body={
                "query": "context",
                "filters": {"episode_id": "rest-ep-2"},
                "query_modes": ["keyword"],
            },
        ),
        ProductTransportScenario(
            name="access_ask_ok",
            method="POST",
            path="/v1/access:ask",
            expected_http_status=200,
            expected_app_status="ok",
            json_body={"query": "alpha"},
            required_nonempty_json_paths=(
                "result.answer_text",
                "result.answer_support_ids",
                "result.answer_trace.provider_family",
                "trace_ref",
            ),
        ),
        ProductTransportScenario(
            name="access_run_flash",
            method="POST",
            path="/v1/access:run",
            expected_http_status=200,
            expected_app_status="ok",
            json_body={"query": "beta", "mode": "flash"},
            expected_json_values={"result.resolved_mode": "flash"},
            required_nonempty_json_paths=("result.answer_text", "trace_ref"),
        ),
        ProductTransportScenario(
            name="access_explain_recall",
            method="POST",
            path="/v1/access:explain",
            expected_http_status=200,
            expected_app_status="ok",
            json_body={"query": "gamma", "mode": "recall"},
            expected_json_values={"result.resolved_mode": "recall"},
            required_nonempty_json_paths=(
                "result.answer_text",
                "result.answer_support_ids",
                "trace_ref",
            ),
        ),
        ProductTransportScenario(
            name="frontend_access_focus",
            method="POST",
            path="/v1/frontend/access",
            expected_http_status=200,
            expected_app_status="ok",
            json_body={
                "query": "alpha",
                "episode_id": "rest-ep-1",
                "depth": "focus",
                "explain": True,
            },
            expected_json_values={"result.resolved_depth": "focus"},
            required_nonempty_json_paths=(
                "result.answer.text",
                "result.answer.support_ids",
                "result.candidate_objects",
                "result.selected_objects",
                "trace_ref",
            ),
        ),
        ProductTransportScenario(
            name="governance_plan_ok",
            method="POST",
            path="/v1/governance:plan-conceal",
            expected_http_status=200,
            expected_app_status="ok",
            json_body={"episode_id": "rest-ep-2", "reason": "transport plan"},
        ),
        ProductTransportScenario(
            name="governance_preview_ok",
            method="POST",
            path="/v1/governance:preview",
            expected_http_status=200,
            expected_app_status="ok",
            json_body={"operation_id": operation_id},
        ),
        ProductTransportScenario(
            name="governance_execute_ok",
            method="POST",
            path="/v1/governance:execute-conceal",
            expected_http_status=200,
            expected_app_status="ok",
            json_body={"operation_id": operation_id},
        ),
        ProductTransportScenario(
            name="job_submit_ok",
            method="POST",
            path="/v1/jobs",
            expected_http_status=200,
            expected_app_status="ok",
            json_body={
                "job_kind": "reflect_episode",
                "payload": {"episode_id": "rest-ep-2", "focus": "transport submit"},
            },
        ),
        ProductTransportScenario(
            name="jobs_list_all",
            method="GET",
            path="/v1/jobs",
            expected_http_status=200,
            expected_app_status="ok",
        ),
        ProductTransportScenario(
            name="jobs_list_pending",
            method="GET",
            path="/v1/jobs",
            expected_http_status=200,
            expected_app_status="ok",
            params=[("status", "pending")],
        ),
        ProductTransportScenario(
            name="job_get_pending",
            method="GET",
            path=f"/v1/jobs/{pending_job_id}",
            expected_http_status=200,
            expected_app_status="ok",
        ),
        ProductTransportScenario(
            name="job_cancel_ok",
            method="DELETE",
            path=f"/v1/jobs/{cancel_job_id}",
            expected_http_status=200,
            expected_app_status="ok",
        ),
        ProductTransportScenario(
            name="job_get_cancelled",
            method="GET",
            path=f"/v1/jobs/{cancel_job_id}",
            expected_http_status=200,
            expected_app_status="ok",
        ),
        ProductTransportScenario(
            name="jobs_list_failed",
            method="GET",
            path="/v1/jobs",
            expected_http_status=200,
            expected_app_status="ok",
            params=[("status", "failed")],
        ),
        ProductTransportScenario(
            name="session_open_update",
            method="POST",
            path="/v1/sessions",
            expected_http_status=200,
            expected_app_status="ok",
            json_body={
                "session_id": session_id,
                "principal_id": principal_id,
                "conversation_id": "conv-rest-updated",
                "client_id": "web",
                "device_id": "browser",
            },
        ),
        ProductTransportScenario(
            name="session_get_updated",
            method="GET",
            path=f"/v1/sessions/{session_id}",
            expected_http_status=200,
            expected_app_status="ok",
        ),
        ProductTransportScenario(
            name="user_preferences_update",
            method="PATCH",
            path=f"/v1/users/{principal_id}/preferences",
            expected_http_status=200,
            expected_app_status="ok",
            json_body={
                "preferences": {
                    "default_access_mode": "flash",
                    "conceal_visibility": True,
                }
            },
        ),
        ProductTransportScenario(
            name="user_defaults_updated",
            method="GET",
            path=f"/v1/users/{principal_id}/defaults",
            expected_http_status=200,
            expected_app_status="ok",
        ),
        ProductTransportScenario(
            name="unauthorized_missing_api_key",
            method="GET",
            path="/v1/system/health",
            expected_http_status=401,
            expected_app_status="unauthorized",
            headers={},
        ),
        ProductTransportScenario(
            name="unauthorized_invalid_api_key",
            method="GET",
            path="/v1/system/health",
            expected_http_status=401,
            expected_app_status="unauthorized",
            headers={"X-API-Key": "wrong-key"},
        ),
        ProductTransportScenario(
            name="jobs_invalid_kind",
            method="POST",
            path="/v1/jobs",
            expected_http_status=400,
            expected_app_status="error",
            json_body={
                "job_kind": "invalid-kind",
                "payload": {"episode_id": "rest-ep-2"},
            },
        ),
        ProductTransportScenario(
            name="job_get_missing",
            method="GET",
            path="/v1/jobs/missing-job",
            expected_http_status=404,
            expected_app_status="not_found",
        ),
        ProductTransportScenario(
            name="user_get_missing",
            method="GET",
            path="/v1/users/missing-principal",
            expected_http_status=404,
            expected_app_status="not_found",
        ),
        ProductTransportScenario(
            name="session_get_missing",
            method="GET",
            path="/v1/sessions/missing-session",
            expected_http_status=404,
            expected_app_status="not_found",
        ),
        ProductTransportScenario(
            name="memory_create_additional",
            method="POST",
            path="/v1/memories",
            expected_http_status=200,
            expected_app_status="ok",
            json_body={
                "content": "delta memory for transport bench",
                "episode_id": "rest-ep-3",
                "timestamp_order": 1,
            },
        ),
    )


def build_product_transport_consistency_scenarios_v1() -> tuple[
    ProductTransportConsistencyScenario, ...
]:
    """Return frozen shared-family consistency scenarios for REST/MCP/CLI audits."""

    scenarios = (
        ProductTransportConsistencyScenario(
            scenario_id="transport-remember-basic",
            command_family="remember",
            summary="Store one memory through REST, MCP, and product CLI.",
            rest_method="POST",
            rest_path="/v1/memories",
            rest_json_body={
                "content": "compare remember",
                "episode_id": "cmp-ep-1",
                "timestamp_order": 1,
            },
            mcp_tool_name="remember",
            mcp_args={
                "content": "compare remember",
                "episode_id": "cmp-ep-1",
                "timestamp_order": 1,
            },
            cli_argv=("mind", "remember", "compare remember", "--episode-id", "cmp-ep-1"),
        ),
        ProductTransportConsistencyScenario(
            scenario_id="transport-recall-keyword",
            command_family="recall",
            summary="Recall seeded memories through REST, MCP, and product CLI.",
            rest_method="POST",
            rest_path="/v1/memories:recall",
            rest_json_body={"query": "seed", "query_modes": ["keyword"]},
            mcp_tool_name="recall",
            mcp_args={"query": "seed", "query_modes": ["keyword"]},
            cli_argv=("mind", "recall", "seed"),
        ),
        ProductTransportConsistencyScenario(
            scenario_id="transport-ask-auto",
            command_family="ask",
            summary="Ask against seeded memories through REST, MCP, and product CLI.",
            rest_method="POST",
            rest_path="/v1/access:ask",
            rest_json_body={"query": "seed"},
            mcp_tool_name="ask_memory",
            mcp_args={"query": "seed"},
            cli_argv=("mind", "ask", "seed"),
        ),
    )
    if len(scenarios) != 3:
        raise RuntimeError(
            "Product transport consistency scenarios expected 3 entries, "
            f"got {len(scenarios)}"
        )
    return scenarios


def normalize_product_transport_payload(command_family: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize one transport payload for shared semantic comparisons."""

    result = payload.get("result") or {}
    if command_family == "remember":
        return {
            "status": payload.get("status"),
            "result_keys": sorted(result.keys()) if isinstance(result, dict) else (),
        }
    if command_family == "recall":
        candidates = result.get("candidates") if isinstance(result, dict) else ()
        if not isinstance(candidates, list):
            candidates = ()
        return {
            "status": payload.get("status"),
            "result_keys": sorted(result.keys()) if isinstance(result, dict) else (),
            "candidate_types": tuple(
                str(candidate.get("object_type") or candidate.get("type") or "unknown")
                for candidate in candidates
                if isinstance(candidate, dict)
            ),
        }
    if command_family == "ask":
        answer_text = result.get("answer_text") if isinstance(result, dict) else None
        support_ids = result.get("answer_support_ids") if isinstance(result, dict) else ()
        if not isinstance(support_ids, list):
            support_ids = ()
        return {
            "status": payload.get("status"),
            "result_keys": sorted(result.keys()) if isinstance(result, dict) else (),
            "resolved_mode": result.get("resolved_mode") if isinstance(result, dict) else None,
            "has_answer_text": isinstance(answer_text, str) and bool(answer_text.strip()),
            "support_count": len(support_ids),
        }
    if command_family == "status":
        if not isinstance(result, dict):
            return {"status": payload.get("status")}
        return {
            "status": payload.get("status"),
            "health": (result.get("health") or {}).get("status"),
            "ready": (result.get("readiness") or {}).get("ready"),
        }
    if command_family == "config":
        if not isinstance(result, dict):
            return {"status": payload.get("status")}
        runtime = result.get("runtime") or {}
        provider = result.get("provider") or {}
        return {
            "status": payload.get("status"),
            "backend": runtime.get("backend"),
            "profile": runtime.get("profile"),
            "provider": provider.get("provider"),
        }
    return payload
