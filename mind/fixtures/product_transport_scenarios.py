"""Product transport scenario fixtures."""

from __future__ import annotations

from dataclasses import dataclass
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
    """Return the v1 transport scenario set for REST verification."""

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
        ),
        ProductTransportScenario(
            name="access_run_flash",
            method="POST",
            path="/v1/access:run",
            expected_http_status=200,
            expected_app_status="ok",
            json_body={"query": "beta", "mode": "flash"},
        ),
        ProductTransportScenario(
            name="access_explain_recall",
            method="POST",
            path="/v1/access:explain",
            expected_http_status=200,
            expected_app_status="ok",
            json_body={"query": "gamma", "mode": "recall"},
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
