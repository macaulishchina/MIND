"""WP-3 REST API verification tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from mind.api.app import create_app
from mind.cli_config import resolve_cli_config
from mind.fixtures.product_transport_scenarios import (
    ProductTransportScenario,
    build_product_transport_scenarios_v1,
)


@pytest.fixture
async def api_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    """Build a test client backed by a temporary SQLite store."""

    monkeypatch.setenv("MIND_API_KEY", "test-api-key")
    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "wp3-rest.sqlite3"),
    )
    app = create_app(config)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            yield client


@pytest.mark.anyio
async def test_auth_and_request_id(api_client: httpx.AsyncClient) -> None:
    missing = await api_client.get("/v1/system/health")
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "authorization_error"

    invalid = await api_client.get("/v1/system/health", headers={"X-API-Key": "wrong"})
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "authorization_error"

    valid = await api_client.get(
        "/v1/system/health",
        headers={"X-API-Key": "test-api-key", "X-Request-ID": "req-rest-auth"},
    )
    assert valid.status_code == 200
    assert valid.headers["X-Request-ID"] == "req-rest-auth"
    assert valid.json()["request_id"] == "req-rest-auth"


@pytest.mark.anyio
async def test_rest_endpoint_workflow_and_error_envelope(
    api_client: httpx.AsyncClient,
) -> None:
    state = await _seed_rest_state(api_client)
    headers = _auth_headers()

    health = await api_client.get("/v1/system/health", headers=headers)
    readiness = await api_client.get("/v1/system/readiness", headers=headers)
    config = await api_client.get("/v1/system/config", headers=headers)
    assert health.status_code == 200
    assert readiness.status_code == 200
    assert config.status_code == 200

    get_memory = await api_client.get(f"/v1/memories/{state['memory_id']}", headers=headers)
    list_memories = await api_client.get("/v1/memories", headers=headers)
    search = await api_client.post(
        "/v1/memories:search",
        headers=headers,
        json={"query": "alpha", "max_candidates": 5},
    )
    recall = await api_client.post(
        "/v1/memories:recall",
        headers=headers,
        json={"query": "alpha", "query_modes": ["keyword"]},
    )
    assert get_memory.status_code == 200
    assert list_memories.status_code == 200
    assert search.status_code == 200
    assert recall.status_code == 200
    assert recall.json()["result"]["candidates"][0]["object_type"] == "RawRecord"

    ask = await api_client.post("/v1/access:ask", headers=headers, json={"query": "alpha"})
    run = await api_client.post(
        "/v1/access:run",
        headers=headers,
        json={"query": "beta", "mode": "flash"},
    )
    explain = await api_client.post(
        "/v1/access:explain",
        headers=headers,
        json={"query": "gamma", "mode": "recall"},
    )
    assert ask.status_code == 200
    assert run.status_code == 200
    assert explain.status_code == 200

    preview = await api_client.post(
        "/v1/governance:preview",
        headers=headers,
        json={"operation_id": state["operation_id"]},
    )
    execute = await api_client.post(
        "/v1/governance:execute-conceal",
        headers=headers,
        json={"operation_id": state["operation_id"]},
    )
    assert preview.status_code == 200
    assert execute.status_code == 200

    get_job = await api_client.get(f"/v1/jobs/{state['pending_job_id']}", headers=headers)
    list_jobs = await api_client.get("/v1/jobs", headers=headers)
    cancel_job = await api_client.delete(
        f"/v1/jobs/{state['cancel_job_id']}",
        headers=headers,
    )
    assert get_job.status_code == 200
    assert list_jobs.status_code == 200
    assert cancel_job.status_code == 200

    get_session = await api_client.get(f"/v1/sessions/{state['session_id']}", headers=headers)
    get_user = await api_client.get(f"/v1/users/{state['principal_id']}", headers=headers)
    patch_user = await api_client.patch(
        f"/v1/users/{state['principal_id']}/preferences",
        headers=headers,
        json={"preferences": {"default_access_mode": "flash"}},
    )
    get_defaults = await api_client.get(
        f"/v1/users/{state['principal_id']}/defaults",
        headers=headers,
    )
    assert get_session.status_code == 200
    assert get_user.status_code == 200
    assert patch_user.status_code == 200
    assert get_defaults.status_code == 200
    assert get_defaults.json()["result"]["default_access_mode"] == "flash"

    missing_memory = await api_client.get("/v1/memories/missing-object", headers=headers)
    assert missing_memory.status_code == 404
    assert missing_memory.json()["status"] == "not_found"
    assert missing_memory.json()["error"]["code"] == "not_found"
    assert "message" in missing_memory.json()["error"]


@pytest.mark.anyio
async def test_rest_pagination(api_client: httpx.AsyncClient) -> None:
    state = await _seed_rest_state(api_client)
    headers = _auth_headers()

    memories_page = await api_client.get(
        "/v1/memories",
        headers=headers,
        params={"limit": 2, "offset": 1},
    )
    assert memories_page.status_code == 200
    assert memories_page.json()["result"]["limit"] == 2
    assert memories_page.json()["result"]["offset"] == 1
    assert len(memories_page.json()["result"]["objects"]) == 2

    jobs_page = await api_client.get(
        "/v1/jobs",
        headers=headers,
        params={"limit": 1, "offset": 1},
    )
    assert jobs_page.status_code == 200
    assert len(jobs_page.json()["result"]["jobs"]) == 1
    assert jobs_page.json()["result"]["total"] >= 2

    filtered_jobs = await api_client.get(
        "/v1/jobs",
        headers=headers,
        params=[("status", "pending")],
    )
    assert filtered_jobs.status_code == 200
    filtered_job_ids = [
        job["job_id"] for job in filtered_jobs.json()["result"]["jobs"]
    ]
    assert state["pending_job_id"] in filtered_job_ids


@pytest.mark.anyio
async def test_product_transport_scenario_set_v1_pass_rate(
    api_client: httpx.AsyncClient,
) -> None:
    state = await _seed_rest_state(api_client)
    scenarios = build_product_transport_scenarios_v1(**state)
    passed = 0

    for scenario in scenarios:
        response = await _run_scenario(api_client, scenario)
        body = response.json()
        if (
            response.status_code == scenario.expected_http_status
            and body["status"] == scenario.expected_app_status
        ):
            passed += 1

    pass_rate = passed / len(scenarios)
    assert len(scenarios) >= 40
    assert pass_rate >= 0.95


async def _seed_rest_state(client: httpx.AsyncClient) -> dict[str, str]:
    headers = _auth_headers()
    principal_id = "user-rest-1"
    session_id = "session-rest-1"

    session_resp = await client.post(
        "/v1/sessions",
        headers=headers,
        json={
            "session_id": session_id,
            "principal_id": principal_id,
            "conversation_id": "conv-rest-1",
            "client_id": "web",
            "device_id": "browser",
        },
    )
    assert session_resp.status_code == 200

    memory_ids: list[str] = []
    memory_payloads = [
        {"content": "alpha memory", "episode_id": "rest-ep-1", "timestamp_order": 1},
        {"content": "beta memory", "episode_id": "rest-ep-1", "timestamp_order": 2},
        {"content": "gamma context", "episode_id": "rest-ep-2", "timestamp_order": 1},
    ]
    for payload in memory_payloads:
        response = await client.post("/v1/memories", headers=headers, json=payload)
        assert response.status_code == 200
        memory_ids.append(response.json()["result"]["object_id"])

    plan = await client.post(
        "/v1/governance:plan-conceal",
        headers=headers,
        json={"episode_id": "rest-ep-1", "reason": "rest workflow"},
    )
    assert plan.status_code == 200
    operation_id = plan.json()["result"]["operation_id"]

    pending_job = await client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "job_kind": "reflect_episode",
            "payload": {"episode_id": "rest-ep-1", "focus": "pending job"},
        },
    )
    cancel_job = await client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "job_kind": "reflect_episode",
            "payload": {"episode_id": "rest-ep-2", "focus": "cancel job"},
        },
    )
    assert pending_job.status_code == 200
    assert cancel_job.status_code == 200

    return {
        "memory_id": memory_ids[0],
        "second_memory_id": memory_ids[1],
        "operation_id": operation_id,
        "pending_job_id": pending_job.json()["result"]["job_id"],
        "cancel_job_id": cancel_job.json()["result"]["job_id"],
        "session_id": session_id,
        "principal_id": principal_id,
    }


def _auth_headers() -> dict[str, str]:
    return {"X-API-Key": "test-api-key"}


async def _run_scenario(
    client: httpx.AsyncClient,
    scenario: ProductTransportScenario,
) -> Any:
    headers = _auth_headers()
    if scenario.headers is not None:
        headers = scenario.headers
    return await client.request(
        scenario.method,
        scenario.path,
        headers=headers,
        json=scenario.json_body,
        params=scenario.params,
    )
