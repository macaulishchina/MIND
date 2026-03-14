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
    provider_status = await api_client.get("/v1/system/provider-status", headers=headers)
    frontend_catalog = await api_client.get("/v1/frontend/catalog", headers=headers)
    frontend_settings = await api_client.get("/v1/frontend/settings", headers=headers)
    assert health.status_code == 200
    assert readiness.status_code == 200
    assert config.status_code == 200
    assert provider_status.status_code == 200
    assert frontend_catalog.status_code == 200
    assert frontend_settings.status_code == 200
    assert frontend_catalog.json()["result"]["bench_version"] == "FrontendExperienceBench v1"
    assert frontend_settings.json()["result"]["runtime"]["backend"] == "sqlite"
    assert provider_status.json()["result"]["provider_family"] == "deterministic"

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
    assert ask.json()["result"]["answer_text"]
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
    filtered_job_ids = [job["job_id"] for job in filtered_jobs.json()["result"]["jobs"]]
    assert state["pending_job_id"] in filtered_job_ids


@pytest.mark.anyio
async def test_frontend_debug_route_requires_server_side_dev_mode(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/v1/frontend/debug:timeline",
        headers=_auth_headers(),
        json={"run_id": "req-front-debug-disabled"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_operation"


@pytest.mark.anyio
async def test_frontend_settings_preview_route_returns_preview(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/v1/frontend/settings:preview",
        headers=_auth_headers(),
        json={
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "endpoint": "https://proxy.example/v1/responses",
            "api_key": "openai-preview-key",
            "dev_mode": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["result"]["preview"]["provider"]["provider"] == "openai"
    assert (
        response.json()["result"]["preview"]["provider"]["endpoint"]
        == "https://proxy.example/v1/chat/completions"
    )
    assert "dev_mode" in response.json()["result"]["changed_keys"]
    assert "endpoint" in response.json()["result"]["changed_keys"]
    assert response.json()["result"]["applied_env_overrides"]["OPENAI_API_KEY"] == "***redacted***"


@pytest.mark.anyio
async def test_provider_status_resolve_route_honors_request_level_selection(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/v1/system/provider-status:resolve",
        headers=_auth_headers(),
        json={
            "provider_selection": {
                "provider": "claude",
                "model": "claude-3-7-sonnet-custom",
                "endpoint": "https://claude.example/v1/messages",
                "timeout_ms": 12_000,
                "retry_policy": "none",
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["provider"] == "claude"
    assert payload["result"]["provider_family"] == "claude"
    assert payload["result"]["model"] == "claude-3-7-sonnet-custom"
    assert payload["result"]["endpoint"] == "https://claude.example/v1/messages"
    assert payload["result"]["timeout_ms"] == 12_000
    assert payload["result"]["retry_policy"] == "none"


@pytest.mark.anyio
async def test_provider_status_resolve_route_returns_validation_error_for_invalid_provider(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/v1/system/provider-status:resolve",
        headers=_auth_headers(),
        json={
            "provider_selection": {
                "provider": "unknown-provider",
                "model": "mystery-model",
            }
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["details"]["provider_selection"]["provider"] == "unknown-provider"


@pytest.mark.anyio
async def test_job_submit_route_persists_request_level_provider_selection(
    api_client: httpx.AsyncClient,
) -> None:
    submit = await api_client.post(
        "/v1/jobs",
        headers=_auth_headers(),
        json={
            "job_kind": "reflect_episode",
            "payload": {
                "episode_id": "rest-job-provider-selection",
                "focus": "persist provider override",
            },
            "provider_selection": {
                "provider": "claude",
                "model": "claude-3-7-sonnet",
                "endpoint": "https://api.anthropic.com/v1/messages",
                "timeout_ms": 8_000,
                "retry_policy": "none",
            },
        },
    )

    assert submit.status_code == 200
    submit_payload = submit.json()
    assert submit_payload["result"]["provider_selection"]["provider"] == "claude"

    get_job = await api_client.get(
        f"/v1/jobs/{submit_payload['result']['job_id']}",
        headers=_auth_headers(),
    )

    assert get_job.status_code == 200
    get_job_payload = get_job.json()
    assert get_job_payload["result"]["provider_selection"]["provider"] == "claude"
    assert get_job_payload["result"]["provider_selection"]["model"] == "claude-3-7-sonnet"


@pytest.mark.anyio
async def test_access_ask_route_returns_validation_error_for_invalid_provider_selection(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/v1/access:ask",
        headers=_auth_headers(),
        json={
            "query": "alpha",
            "provider_selection": {
                "provider": "unknown-provider",
                "model": "mystery-model",
            },
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["details"]["provider_selection"]["provider"] == "unknown-provider"


@pytest.mark.anyio
async def test_frontend_settings_apply_route_updates_live_frontend_runtime(
    api_client: httpx.AsyncClient,
) -> None:
    headers = _auth_headers()

    initial_debug = await api_client.post(
        "/v1/frontend/debug:timeline",
        headers=headers,
        json={"run_id": "req-front-debug-before"},
    )
    apply_response = await api_client.post(
        "/v1/frontend/settings:apply",
        headers=headers,
        json={"provider": "openai", "model": "gpt-4.1-mini", "dev_mode": True},
    )
    page = await api_client.get("/v1/frontend/settings", headers=headers)
    debug_after = await api_client.post(
        "/v1/frontend/debug:timeline",
        headers=headers,
        json={"run_id": "req-front-debug-after"},
    )

    assert initial_debug.status_code == 400
    assert apply_response.status_code == 200
    assert page.status_code == 200
    assert page.json()["result"]["provider"]["provider"] == "openai"
    assert page.json()["result"]["runtime"]["dev_mode"] is True
    assert debug_after.status_code == 200


@pytest.mark.anyio
async def test_frontend_settings_apply_route_persists_llm_overrides(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/v1/frontend/settings:apply",
        headers=_auth_headers(),
        json={
            "provider": "gemini",
            "model": "gemini-2.0-flash-lite",
            "endpoint": "https://proxy.example/v1beta/models",
            "api_key": "gemini-live-key",
        },
    )
    page = await api_client.get("/v1/frontend/settings", headers=_auth_headers())

    assert response.status_code == 200
    assert page.status_code == 200
    payload = page.json()["result"]
    assert payload["provider"]["provider"] == "gemini"
    assert payload["provider"]["endpoint"] == "https://proxy.example/v1beta/models"
    service_view = next(item for item in payload["llm"]["services"] if item["protocol"] == "gemini")
    assert service_view["service_id"] == "managed-gemini"
    assert service_view["active_model"] == "gemini-2.0-flash-lite"
    assert service_view["endpoint"] == "https://proxy.example/v1beta"
    assert service_view["uses_official_endpoint"] is False
    assert service_view["api_key_saved"] is True
    assert service_view["api_key_masked"] == "gemi***-key"


@pytest.mark.anyio
async def test_frontend_llm_service_routes_manage_services(
    api_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    class _FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self) -> _FakeResponse:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    def _fake_urlopen(request: Any, timeout: float = 10.0) -> _FakeResponse:
        assert request.full_url == "https://proxy.example/v1/models"
        assert timeout == 10.0
        return _FakeResponse({"data": [{"id": "gpt-4.1-mini"}, {"id": "gpt-4o-mini"}]})

    monkeypatch.setattr("mind.app.frontend_llm_services.urlopen", _fake_urlopen)

    upsert = await api_client.post(
        "/v1/frontend/llm/services:upsert",
        headers=_auth_headers(),
        json={
            "protocol": "openai",
            "name": "公司代理",
            "endpoint": "https://proxy.example/v1/responses",
            "api_key": "proxy-key",
        },
    )
    assert upsert.status_code == 200
    service_id = upsert.json()["result"]["service_id"]

    discover = await api_client.post(
        "/v1/frontend/llm/services:discover-models",
        headers=_auth_headers(),
        json={"service_id": service_id},
    )
    activate = await api_client.post(
        "/v1/frontend/llm/services:activate",
        headers=_auth_headers(),
        json={"service_id": service_id, "model": "gpt-4o-mini"},
    )
    page = await api_client.get("/v1/frontend/settings", headers=_auth_headers())

    assert discover.status_code == 200
    assert discover.json()["result"]["models"] == ["gpt-4.1-mini", "gpt-4o-mini"]
    assert activate.status_code == 200
    assert activate.json()["result"] == {
        "service_id": service_id,
        "protocol": "openai",
        "model": "gpt-4o-mini",
    }
    assert page.status_code == 200
    payload = page.json()["result"]
    assert payload["provider"]["provider"] == "openai"
    assert payload["llm"]["active_service_id"] == service_id
    service_view = next(
        item for item in payload["llm"]["services"] if item["service_id"] == service_id
    )
    assert service_view["name"] == "公司代理"
    assert service_view["active_model"] == "gpt-4o-mini"
    assert service_view["endpoint"] == "https://proxy.example/v1"
    assert service_view["model_options"] == ["gpt-4.1-mini", "gpt-4o-mini"]


@pytest.mark.anyio
async def test_frontend_llm_service_delete_route_removes_active_service(
    api_client: httpx.AsyncClient,
) -> None:
    upsert = await api_client.post(
        "/v1/frontend/llm/services:upsert",
        headers=_auth_headers(),
        json={
            "protocol": "openai",
            "name": "DeepSeek",
            "endpoint": "https://api.deepseek.com",
            "model": "deepseek-chat",
        },
    )
    assert upsert.status_code == 200
    service_id = upsert.json()["result"]["service_id"]

    activate = await api_client.post(
        "/v1/frontend/llm/services:activate",
        headers=_auth_headers(),
        json={"service_id": service_id, "model": "deepseek-chat"},
    )
    assert activate.status_code == 200

    deleted = await api_client.post(
        "/v1/frontend/llm/services:delete",
        headers=_auth_headers(),
        json={"service_id": service_id},
    )
    page = await api_client.get("/v1/frontend/settings", headers=_auth_headers())

    assert deleted.status_code == 200
    assert deleted.json()["result"] == {
        "action": "deleted",
        "service_id": service_id,
    }
    assert page.status_code == 200
    payload = page.json()["result"]
    assert payload["provider"]["provider"] == "deterministic"
    assert payload["llm"]["active_service_id"] is None
    assert payload["llm"]["services"] == []


@pytest.mark.anyio
async def test_editing_active_frontend_llm_service_updates_live_runtime(
    api_client: httpx.AsyncClient,
) -> None:
    initial = await api_client.post(
        "/v1/frontend/llm/services:upsert",
        headers=_auth_headers(),
        json={
            "protocol": "openai",
            "name": "OpenAI 官方",
            "endpoint": "https://api.openai.com/v1",
            "api_key": "openai-old-key",
            "model": "gpt-4.1-mini",
        },
    )
    assert initial.status_code == 200
    service_id = initial.json()["result"]["service_id"]

    activate = await api_client.post(
        "/v1/frontend/llm/services:activate",
        headers=_auth_headers(),
        json={"service_id": service_id, "model": "gpt-4.1-mini"},
    )
    assert activate.status_code == 200

    edited = await api_client.post(
        "/v1/frontend/llm/services:upsert",
        headers=_auth_headers(),
        json={
            "service_id": service_id,
            "protocol": "openai",
            "name": "OpenAI 官方",
            "endpoint": "https://api.deepseek.com/v1",
            "api_key": "deepseek-live-key",
            "model": "deepseek-chat",
        },
    )
    page = await api_client.get("/v1/frontend/settings", headers=_auth_headers())

    assert edited.status_code == 200
    assert page.status_code == 200
    payload = page.json()["result"]
    assert payload["llm"]["active_service_id"] == service_id
    assert payload["provider"]["provider"] == "openai"
    assert payload["provider"]["endpoint"] == "https://api.deepseek.com/v1/chat/completions"
    service_view = next(
        item for item in payload["llm"]["services"] if item["service_id"] == service_id
    )
    assert service_view["endpoint"] == "https://api.deepseek.com/v1"
    assert service_view["active_model"] == "deepseek-chat"
    assert service_view["is_active"] is True


@pytest.mark.anyio
async def test_frontend_settings_restore_route_fails_without_previous_snapshot(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/v1/frontend/settings:restore",
        headers=_auth_headers(),
        json={},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.anyio
async def test_frontend_experience_routes_project_product_flows(
    api_client: httpx.AsyncClient,
) -> None:
    headers = _auth_headers()
    episode_id = "front-rest-ep-1"

    ingest = await api_client.post(
        "/v1/frontend/ingest",
        headers=headers,
        json={
            "content": "frontend route ingest seed",
            "episode_id": episode_id,
            "timestamp_order": 1,
        },
    )
    assert ingest.status_code == 200
    ingest_result = ingest.json()["result"]
    assert ingest_result["object_id"].startswith("raw-")
    assert ingest_result["episode_id"] == episode_id

    retrieve = await api_client.post(
        "/v1/frontend/retrieve",
        headers=headers,
        json={
            "query": "frontend route ingest",
            "episode_id": episode_id,
            "max_candidates": 5,
        },
    )
    assert retrieve.status_code == 200
    retrieve_result = retrieve.json()["result"]
    assert retrieve_result["candidate_count"] >= 1
    assert retrieve_result["candidates"][0]["object_id"] == ingest_result["object_id"]

    access = await api_client.post(
        "/v1/frontend/access",
        headers=headers,
        json={
            "query": "what was stored for the frontend route?",
            "episode_id": episode_id,
            "depth": "focus",
            "explain": True,
        },
    )
    assert access.status_code == 200
    access_result = access.json()["result"]
    assert access_result["resolved_depth"] == "focus"
    assert access_result["candidate_count"] >= 1
    assert access_result["answer"]["text"]
    assert access_result["answer"]["support_ids"]

    offline = await api_client.post(
        "/v1/frontend/offline",
        headers=headers,
        json={
            "job_kind": "reflect_episode",
            "payload": {
                "episode_id": episode_id,
                "focus": "frontend route reflection",
            },
        },
    )
    assert offline.status_code == 200
    assert offline.json()["result"]["status"] == "pending"


@pytest.mark.anyio
async def test_frontend_ingest_route_accepts_missing_episode_id(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/v1/frontend/ingest",
        headers=_auth_headers(),
        json={
            "content": "frontend route ingest without explicit episode",
            "timestamp_order": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()["result"]["object_id"].startswith("raw-")
    assert response.json()["result"]["episode_id"].startswith("ep-")


@pytest.mark.anyio
async def test_frontend_gate_demo_route_returns_summary_surface(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/v1/frontend/gate-demo", headers=_auth_headers())

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["page_version"] == "FrontendGateDemoPage v1"
    assert len(result["entries"]) == 7
    assert result["entries"][0]["kind"] == "demo"


@pytest.mark.anyio
async def test_frontend_debug_route_projects_persisted_telemetry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MIND_API_KEY", "test-api-key")
    monkeypatch.setenv("MIND_DEV_MODE", "true")
    monkeypatch.setenv("MIND_DEV_TELEMETRY_PATH", str(tmp_path / "telemetry.jsonl"))

    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "wp3-frontend-debug.sqlite3"),
        allow_sqlite=True,
    )
    app = create_app(config)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            headers = _auth_headers()
            remember = await client.post(
                "/v1/memories",
                headers={**headers, "X-Request-ID": "req-front-debug-enabled"},
                json={
                    "content": "frontend debug api memory",
                    "episode_id": "front-debug-ep-1",
                    "timestamp_order": 1,
                },
            )
            assert remember.status_code == 200

            timeline = await client.post(
                "/v1/frontend/debug:timeline",
                headers=headers,
                json={
                    "run_id": "req-front-debug-enabled",
                    "include_state_deltas": True,
                },
            )

    assert timeline.status_code == 200
    assert timeline.json()["result"]["returned_event_count"] >= 3
    assert len(timeline.json()["result"]["object_deltas"]) >= 1
    assert "context_views" in timeline.json()["result"]
    assert "evidence_views" in timeline.json()["result"]


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
        if _scenario_matches(response, body, scenario):
            passed += 1

    pass_rate = passed / len(scenarios)
    assert len(scenarios) >= 40
    assert pass_rate >= 0.95


def test_product_transport_scenario_set_v1_includes_frontend_contract_checks() -> None:
    scenarios = build_product_transport_scenarios_v1(
        memory_id="memory-1",
        second_memory_id="memory-2",
        operation_id="op-1",
        pending_job_id="job-1",
        cancel_job_id="job-2",
        session_id="session-1",
        principal_id="user-1",
    )
    by_name = {scenario.name: scenario for scenario in scenarios}

    frontend_access = by_name["frontend_access_focus"]
    assert frontend_access.expected_json_values["result.resolved_depth"] == "focus"
    assert "result.answer.text" in frontend_access.required_nonempty_json_paths
    assert "result.answer.support_ids" in frontend_access.required_nonempty_json_paths

    access_ask = by_name["access_ask_ok"]
    assert "result.answer_text" in access_ask.required_nonempty_json_paths
    assert "result.answer_support_ids" in access_ask.required_nonempty_json_paths
    assert "result.answer_trace.provider_family" in access_ask.required_nonempty_json_paths


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


def _scenario_matches(
    response: Any,
    body: dict[str, Any],
    scenario: ProductTransportScenario,
) -> bool:
    if response.status_code != scenario.expected_http_status:
        return False
    if body.get("status") != scenario.expected_app_status:
        return False
    for path in scenario.required_json_paths:
        found, _ = _json_path_lookup(body, path)
        if not found:
            return False
    for path in scenario.required_nonempty_json_paths:
        found, value = _json_path_lookup(body, path)
        if not found or _is_empty_value(value):
            return False
    for path, expected in scenario.expected_json_values.items():
        found, value = _json_path_lookup(body, path)
        if not found or value != expected:
            return False
    return True


def _json_path_lookup(payload: Any, path: str) -> tuple[bool, Any]:
    current = payload
    for segment in path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                return False, None
            current = current[segment]
            continue
        if isinstance(current, list) and segment.isdigit():
            index = int(segment)
            if index >= len(current):
                return False, None
            current = current[index]
            continue
        return False, None
    return True, current


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list | tuple | set | dict):
        return len(value) == 0
    return False
