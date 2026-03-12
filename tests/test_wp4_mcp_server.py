"""WP-4 MCP server verification tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest

from mind.api.app import create_app
from mind.app.context import PrincipalContext, PrincipalKind, SourceChannel
from mind.app.contracts import AppRequest, AppStatus
from mind.app.registry import build_app_registry
from mind.cli_config import ResolvedCliConfig, resolve_cli_config
from mind.fixtures import (
    build_product_transport_consistency_scenarios_v1,
    normalize_product_transport_payload,
)
from mind.mcp.server import create_mcp_server
from mind.mcp.session import map_mcp_session
from mind.primitives.contracts import Capability


def test_mcp_tool_catalog_lists_all_11_tools(tmp_path: Path) -> None:
    config = _sqlite_config(tmp_path, "catalog")
    with create_mcp_server(config) as server:
        tool_names = [tool.name for tool in server.list_tools()]

    assert tool_names == [
        "remember",
        "recall",
        "ask_memory",
        "get_memory",
        "list_memories",
        "search_memories",
        "plan_conceal",
        "preview_conceal",
        "execute_conceal",
        "submit_offline_job",
        "get_job_status",
    ]


def test_mcp_tool_invocations_return_expected_shapes(tmp_path: Path) -> None:
    config = _sqlite_config(tmp_path, "invocations")
    client_info = _mcp_client_info()

    with create_mcp_server(config) as server:
        remember = server.invoke_tool(
            "remember",
            {
                "content": "mcp memory",
                "episode_id": "mcp-ep-1",
                "timestamp_order": 1,
            },
            client_info=client_info,
        )
        memory_id = remember["result"]["object_id"]

        get_memory = server.invoke_tool(
            "get_memory",
            {"object_id": memory_id},
            client_info=client_info,
        )
        list_memories = server.invoke_tool("list_memories", {}, client_info=client_info)
        search = server.invoke_tool(
            "search_memories",
            {"query": "mcp", "max_candidates": 5},
            client_info=client_info,
        )
        recall = server.invoke_tool(
            "recall",
            {"query": "mcp", "query_modes": ["keyword"]},
            client_info=client_info,
        )
        ask = server.invoke_tool(
            "ask_memory",
            {"query": "mcp"},
            client_info=client_info,
        )
        plan = server.invoke_tool(
            "plan_conceal",
            {"episode_id": "mcp-ep-1", "reason": "mcp test"},
            client_info=client_info,
        )
        preview = server.invoke_tool(
            "preview_conceal",
            {"operation_id": plan["result"]["operation_id"]},
            client_info=client_info,
        )
        execute = server.invoke_tool(
            "execute_conceal",
            {"operation_id": plan["result"]["operation_id"]},
            client_info=client_info,
        )
        submit_job = server.invoke_tool(
            "submit_offline_job",
            {
                "job_kind": "reflect_episode",
                "payload": {"episode_id": "mcp-ep-1", "focus": "mcp job"},
            },
            client_info=client_info,
        )
        job_status = server.invoke_tool(
            "get_job_status",
            {"job_id": submit_job["result"]["job_id"]},
            client_info=client_info,
        )

    assert remember["status"] == "ok"
    assert "object_id" in remember["result"]
    assert get_memory["result"]["object"]["id"] == memory_id
    assert list_memories["result"]["total"] >= 1
    assert "matches" in search["result"]
    assert recall["status"] == "ok"
    assert ask["status"] == "ok"
    assert "operation_id" in plan["result"]
    assert preview["status"] == "ok"
    assert execute["status"] == "ok"
    assert submit_job["result"]["status"] == "pending"
    assert job_status["result"]["job_id"] == submit_job["result"]["job_id"]


def test_mcp_submit_offline_job_persists_request_level_provider_selection(
    tmp_path: Path,
) -> None:
    config = _sqlite_config(tmp_path, "job-provider-selection")
    client_info = _mcp_client_info()

    with create_mcp_server(config) as server:
        submit_job = server.invoke_tool(
            "submit_offline_job",
            {
                "job_kind": "reflect_episode",
                "payload": {
                    "episode_id": "mcp-job-provider-selection",
                    "focus": "persist provider override",
                },
                "provider_selection": {
                    "provider": "gemini",
                    "model": "gemini-2.0-flash",
                    "endpoint": "https://generativelanguage.googleapis.com/v1beta/models",
                    "timeout_ms": 9_000,
                    "retry_policy": "aggressive",
                },
            },
            client_info=client_info,
        )
        job_status = server.invoke_tool(
            "get_job_status",
            {"job_id": submit_job["result"]["job_id"]},
            client_info=client_info,
        )

    assert submit_job["status"] == "ok"
    assert submit_job["result"]["provider_selection"]["provider"] == "gemini"
    assert job_status["result"]["provider_selection"]["provider"] == "gemini"
    assert job_status["result"]["provider_selection"]["model"] == "gemini-2.0-flash"


def test_mcp_ask_memory_returns_validation_error_for_invalid_provider_selection(
    tmp_path: Path,
) -> None:
    config = _sqlite_config(tmp_path, "ask-invalid-provider")
    client_info = _mcp_client_info()

    with create_mcp_server(config) as server:
        remember = server.invoke_tool(
            "remember",
            {
                "content": "mcp ask invalid provider seed",
                "episode_id": "mcp-ask-invalid-provider",
                "timestamp_order": 1,
            },
            client_info=client_info,
        )
        assert remember["status"] == "ok"

        ask = server.invoke_tool(
            "ask_memory",
            {
                "query": "mcp",
                "provider_selection": {
                    "provider": "unknown-provider",
                    "model": "mystery-model",
                },
            },
            client_info=client_info,
        )

    assert ask["status"] == "error"
    assert ask["error"]["code"] == "validation_error"
    assert ask["error"]["details"]["provider_selection"]["provider"] == "unknown-provider"


@pytest.mark.anyio
async def test_rest_vs_mcp_semantic_consistency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MIND_API_KEY", "test-api-key")
    rest_config = _sqlite_config(tmp_path, "rest")
    mcp_config = _sqlite_config(tmp_path, "mcp")
    rest_state = _seed_transport_state(rest_config)
    mcp_state = _seed_transport_state(mcp_config)
    matches = 0

    async with _rest_client(rest_config) as rest_client:
        with create_mcp_server(mcp_config) as mcp_server:
            matches += await _compare_semantics(
                rest_client=rest_client,
                rest_method="POST",
                rest_path="/v1/memories",
                rest_json={
                    "content": "consistency remember",
                    "episode_id": "cmp-remember",
                    "timestamp_order": 1,
                },
                mcp_server=mcp_server,
                tool_name="remember",
                mcp_args={
                    "content": "consistency remember",
                    "episode_id": "cmp-remember",
                    "timestamp_order": 1,
                },
                normalizer=_normalize_remember_like,
            )
            matches += await _compare_semantics(
                rest_client=rest_client,
                rest_method="POST",
                rest_path="/v1/memories:recall",
                rest_json={"query": "seed", "query_modes": ["keyword"]},
                mcp_server=mcp_server,
                tool_name="recall",
                mcp_args={"query": "seed", "query_modes": ["keyword"]},
                normalizer=_normalize_recall_like,
            )
            matches += await _compare_semantics(
                rest_client=rest_client,
                rest_method="POST",
                rest_path="/v1/access:ask",
                rest_json={"query": "seed"},
                mcp_server=mcp_server,
                tool_name="ask_memory",
                mcp_args={"query": "seed"},
                normalizer=_normalize_access_like,
            )
            matches += await _compare_semantics(
                rest_client=rest_client,
                rest_method="GET",
                rest_path=f"/v1/memories/{rest_state['memory_id']}",
                mcp_server=mcp_server,
                tool_name="get_memory",
                mcp_args={"object_id": mcp_state["memory_id"]},
                normalizer=_normalize_get_memory,
            )
            matches += await _compare_semantics(
                rest_client=rest_client,
                rest_method="GET",
                rest_path="/v1/memories",
                mcp_server=mcp_server,
                tool_name="list_memories",
                mcp_args={},
                normalizer=_normalize_list_memories,
            )
            matches += await _compare_semantics(
                rest_client=rest_client,
                rest_method="POST",
                rest_path="/v1/memories:search",
                rest_json={"query": "seed", "max_candidates": 10},
                mcp_server=mcp_server,
                tool_name="search_memories",
                mcp_args={"query": "seed", "max_candidates": 10},
                normalizer=_normalize_search_memories,
            )
            matches += await _compare_semantics(
                rest_client=rest_client,
                rest_method="POST",
                rest_path="/v1/governance:plan-conceal",
                rest_json={"episode_id": "seed-ep-2", "reason": "cmp plan"},
                mcp_server=mcp_server,
                tool_name="plan_conceal",
                mcp_args={"episode_id": "seed-ep-2", "reason": "cmp plan"},
                normalizer=_normalize_plan_conceal,
            )
            matches += await _compare_semantics(
                rest_client=rest_client,
                rest_method="POST",
                rest_path="/v1/governance:preview",
                rest_json={"operation_id": rest_state["operation_id"]},
                mcp_server=mcp_server,
                tool_name="preview_conceal",
                mcp_args={"operation_id": mcp_state["operation_id"]},
                normalizer=_normalize_preview_conceal,
            )
            matches += await _compare_semantics(
                rest_client=rest_client,
                rest_method="POST",
                rest_path="/v1/governance:execute-conceal",
                rest_json={"operation_id": rest_state["operation_id"]},
                mcp_server=mcp_server,
                tool_name="execute_conceal",
                mcp_args={"operation_id": mcp_state["operation_id"]},
                normalizer=_normalize_execute_conceal,
            )
            matches += await _compare_semantics(
                rest_client=rest_client,
                rest_method="POST",
                rest_path="/v1/jobs",
                rest_json={
                    "job_kind": "reflect_episode",
                    "payload": {"episode_id": "seed-ep-2", "focus": "cmp job"},
                },
                mcp_server=mcp_server,
                tool_name="submit_offline_job",
                mcp_args={
                    "job_kind": "reflect_episode",
                    "payload": {"episode_id": "seed-ep-2", "focus": "cmp job"},
                },
                normalizer=_normalize_submit_job,
            )
            matches += await _compare_semantics(
                rest_client=rest_client,
                rest_method="GET",
                rest_path=f"/v1/jobs/{rest_state['job_id']}",
                mcp_server=mcp_server,
                tool_name="get_job_status",
                mcp_args={"job_id": mcp_state["job_id"]},
                normalizer=_normalize_get_job_status,
            )

    pass_rate = matches / 11
    assert pass_rate >= 0.95


@pytest.mark.anyio
async def test_product_transport_consistency_scenarios_v1_rest_mcp_pass_rate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MIND_API_KEY", "test-api-key")
    rest_config = _sqlite_config(tmp_path, "shared-rest")
    mcp_config = _sqlite_config(tmp_path, "shared-mcp")
    _seed_transport_state(rest_config)
    _seed_transport_state(mcp_config)
    scenarios = [
        scenario
        for scenario in build_product_transport_consistency_scenarios_v1()
        if scenario.mcp_tool_name is not None
    ]
    matches = 0

    async with _rest_client(rest_config) as rest_client:
        with create_mcp_server(mcp_config) as mcp_server:
            for scenario in scenarios:
                matches += await _compare_semantics(
                    rest_client=rest_client,
                    rest_method=scenario.rest_method,
                    rest_path=scenario.rest_path,
                    rest_json=scenario.rest_json_body,
                    mcp_server=mcp_server,
                    tool_name=str(scenario.mcp_tool_name),
                    mcp_args=dict(scenario.mcp_args),
                    normalizer=lambda payload, family=scenario.command_family: (
                        normalize_product_transport_payload(family, payload)
                    ),
                )

    assert len(scenarios) >= 3
    assert matches / len(scenarios) >= 0.95


@pytest.mark.parametrize(
    ("client_info", "expected_principal", "expected_session", "expected_channel"),
    [
        (
            {
                "client_id": "claude-desktop",
                "tenant_id": "acme",
                "conversation_id": "conv-1",
                "device_id": "laptop",
            },
            "claude-desktop",
            "conv-1",
            SourceChannel.MCP,
        ),
        (
            {
                "principal_id": "svc-planner",
                "principal_kind": PrincipalKind.SERVICE,
                "session_id": "session-2",
                "request_id": "req-2",
            },
            "svc-planner",
            "session-2",
            SourceChannel.MCP,
        ),
        (
            {
                "principal": {
                    "principal_id": "explicit-principal",
                    "tenant_id": "tenant-3",
                    "roles": ["planner"],
                    "capabilities": [Capability.MEMORY_READ.value],
                },
                "session": {
                    "session_id": "session-3",
                    "conversation_id": "conv-3",
                    "client_id": "custom-client",
                },
            },
            "explicit-principal",
            "session-3",
            SourceChannel.MCP,
        ),
    ],
)
def test_mcp_session_mapping(
    client_info: dict[str, Any],
    expected_principal: str,
    expected_session: str,
    expected_channel: SourceChannel,
) -> None:
    principal, session = map_mcp_session(client_info, request_id="req-fixed")

    assert principal.principal_id == expected_principal
    assert session.session_id == expected_session
    assert session.channel is expected_channel
    assert session.request_id == "req-fixed"


def _sqlite_config(tmp_path: Path, name: str) -> ResolvedCliConfig:
    return resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / f"{name}.sqlite3"),
    )


def _seed_transport_state(config: ResolvedCliConfig) -> dict[str, str]:
    principal = PrincipalContext(
        principal_id="seed-operator",
        tenant_id="default",
        capabilities=list(Capability),
    )
    with build_app_registry(config) as registry:
        remember_one = registry.memory_ingest_service.remember(
            AppRequest(
                request_id="seed-1",
                principal=principal,
                input={
                    "content": "seed alpha",
                    "episode_id": "seed-ep-1",
                    "timestamp_order": 1,
                },
            )
        )
        registry.memory_ingest_service.remember(
            AppRequest(
                request_id="seed-2",
                principal=principal,
                input={
                    "content": "seed beta",
                    "episode_id": "seed-ep-2",
                    "timestamp_order": 1,
                },
            )
        )
        plan = registry.governance_app_service.plan_conceal(
            AppRequest(
                request_id="seed-3",
                principal=principal,
                input={"episode_id": "seed-ep-1", "reason": "seed plan"},
            )
        )
        job = registry.offline_job_app_service.submit_job(
            AppRequest(
                request_id="seed-4",
                principal=principal,
                input={
                    "job_kind": "reflect_episode",
                    "payload": {"episode_id": "seed-ep-1", "focus": "seed job"},
                },
            )
        )

    assert remember_one.status is AppStatus.OK
    assert plan.status is AppStatus.OK
    assert job.status is AppStatus.OK
    assert remember_one.result is not None
    assert plan.result is not None
    assert job.result is not None
    return {
        "memory_id": str(remember_one.result["object_id"]),
        "operation_id": str(plan.result["operation_id"]),
        "job_id": str(job.result["job_id"]),
    }


@asynccontextmanager
async def _rest_client(config: ResolvedCliConfig) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(config)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            yield client


async def _compare_semantics(
    *,
    rest_client: httpx.AsyncClient,
    rest_method: str,
    rest_path: str,
    mcp_server: Any,
    tool_name: str,
    mcp_args: dict[str, Any],
    normalizer: Any,
    rest_json: dict[str, Any] | None = None,
) -> int:
    rest_response = await rest_client.request(
        rest_method,
        rest_path,
        headers={"X-API-Key": "test-api-key"},
        json=rest_json,
    )
    mcp_response = mcp_server.invoke_tool(
        tool_name,
        mcp_args,
        client_info=_mcp_client_info(),
    )
    if rest_response.status_code != 200:
        return 0
    if rest_response.json()["status"] != mcp_response["status"]:
        return 0
    return int(normalizer(rest_response.json()) == normalizer(mcp_response))


def _mcp_client_info() -> dict[str, Any]:
    return {
        "client_id": "mcp-tester",
        "tenant_id": "default",
        "conversation_id": "mcp-conv",
        "device_id": "local",
    }


def _normalize_remember_like(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    return {
        "status": payload["status"],
        "result_keys": sorted(result.keys()),
    }


def _normalize_recall_like(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    return {
        "status": payload["status"],
        "result_keys": sorted(result.keys()),
    }


def _normalize_access_like(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    return {
        "status": payload["status"],
        "result_keys": sorted(result.keys()),
        "selected_mode": result.get("selected_mode"),
    }


def _normalize_get_memory(payload: dict[str, Any]) -> dict[str, Any]:
    obj = payload["result"]["object"]
    return {
        "status": payload["status"],
        "type": obj["type"],
        "content": obj["content"],
        "episode_id": obj["metadata"].get("episode_id"),
    }


def _normalize_list_memories(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    return {
        "status": payload["status"],
        "count": len(result["objects"]),
        "total": result["total"],
    }


def _normalize_search_memories(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    return {
        "status": payload["status"],
        "total": result["total"],
    }


def _normalize_plan_conceal(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    return {
        "status": payload["status"],
        "candidate_count": len(result["candidate_object_ids"]),
        "already_concealed_count": len(result["already_concealed_object_ids"]),
    }


def _normalize_preview_conceal(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    return {
        "status": payload["status"],
        "candidate_count": len(result["candidate_object_ids"]),
        "already_concealed_count": len(result["already_concealed_object_ids"]),
    }


def _normalize_execute_conceal(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    return {
        "status": payload["status"],
        "concealed_count": len(result["concealed_object_ids"]),
        "already_concealed_count": len(result["already_concealed_object_ids"]),
    }


def _normalize_submit_job(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    return {
        "status": payload["status"],
        "job_status": result["status"],
        "result_keys": sorted(result.keys()),
    }


def _normalize_get_job_status(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    return {
        "status": payload["status"],
        "job_kind": result["job_kind"],
        "job_status": result["status"],
    }
