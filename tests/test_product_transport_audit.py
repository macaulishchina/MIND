from __future__ import annotations

import io
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import httpx
import pytest

from mind.api.app import create_app
from mind.app.registry import build_app_registry
from mind.cli_config import ResolvedCliConfig, resolve_cli_config
from mind.cli import product_transport_report_main
from mind.fixtures import (
    assert_product_transport_audit,
    build_product_transport_consistency_scenarios_v1,
    evaluate_product_transport_audit_report,
    read_product_transport_audit_json,
    render_product_transport_audit_markdown,
    write_product_transport_audit_markdown,
    write_product_transport_audit_json,
)
from mind.mcp.server import create_mcp_server
from mind.product_cli import LocalProductClient, product_main


@pytest.mark.anyio
async def test_product_transport_audit_report_passes_on_current_transports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MIND_API_KEY", "test-api-key")
    rest_path = tmp_path / "transport-audit-rest.sqlite3"
    mcp_path = tmp_path / "transport-audit-mcp.sqlite3"
    cli_path = tmp_path / "transport-audit-cli.sqlite3"
    _seed_backend(rest_path)
    _seed_backend(mcp_path)
    _seed_backend(cli_path)

    scenarios = build_product_transport_consistency_scenarios_v1()
    async with _rest_client(_sqlite_config(rest_path)) as rest_client:
        with create_mcp_server(_sqlite_config(mcp_path)) as mcp_server:
            report = await evaluate_product_transport_audit_report(
                scenarios=scenarios,
                rest_runner=lambda scenario: _run_rest(rest_client, scenario),
                mcp_runner=lambda scenario: _run_mcp(mcp_server, scenario),
                cli_runner=lambda scenario: _run_cli(cli_path, scenario),
            )

    assert report.schema_version == "product_transport_audit_v1"
    assert report.bench_version == "ProductTransportConsistencyScenarios v1"
    assert report.scenario_count == len(scenarios)
    assert report.passed_count == len(scenarios)
    assert report.rest_mcp_pair_count == len(scenarios)
    assert report.rest_cli_pair_count == len(scenarios)
    assert report.rest_mcp_pass_rate >= 0.95
    assert report.rest_cli_pass_rate >= 0.95
    assert report.passed is True
    assert_product_transport_audit(report)


@pytest.mark.anyio
async def test_product_transport_audit_report_round_trips_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MIND_API_KEY", "test-api-key")
    rest_path = tmp_path / "transport-audit-json-rest.sqlite3"
    mcp_path = tmp_path / "transport-audit-json-mcp.sqlite3"
    cli_path = tmp_path / "transport-audit-json-cli.sqlite3"
    _seed_backend(rest_path)
    _seed_backend(mcp_path)
    _seed_backend(cli_path)

    async with _rest_client(_sqlite_config(rest_path)) as rest_client:
        with create_mcp_server(_sqlite_config(mcp_path)) as mcp_server:
            report = await evaluate_product_transport_audit_report(
                rest_runner=lambda scenario: _run_rest(rest_client, scenario),
                mcp_runner=lambda scenario: _run_mcp(mcp_server, scenario),
                cli_runner=lambda scenario: _run_cli(cli_path, scenario),
            )

    output_path = write_product_transport_audit_json(
        tmp_path / "product_transport_audit.json",
        report,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    restored = read_product_transport_audit_json(output_path)

    assert payload["schema_version"] == "product_transport_audit_v1"
    assert payload["passed"] is True
    assert payload["rest_mcp_pass_rate"] >= 0.95
    assert payload["rest_cli_pass_rate"] >= 0.95
    assert restored == report


@pytest.mark.anyio
async def test_product_transport_audit_report_detects_cli_mismatch() -> None:
    scenario = build_product_transport_consistency_scenarios_v1()[0]
    report = await evaluate_product_transport_audit_report(
        scenarios=(scenario,),
        rest_runner=lambda _: {"status": "ok", "result": {"object_id": "obj-1"}},
        mcp_runner=lambda _: {"status": "ok", "result": {"object_id": "obj-2"}},
        cli_runner=lambda _: {"status": "ok", "result": {"candidates": []}},
    )

    assert report.passed is False
    assert report.failure_ids == (scenario.scenario_id,)
    assert report.rest_mcp_pass_rate == 1.0
    assert report.rest_cli_pass_rate == 0.0
    assert report.scenario_results[0].rest_mcp_match is True
    assert report.scenario_results[0].rest_cli_match is False
    assert "rest_cli_mismatch" in report.scenario_results[0].failure_reasons


@pytest.mark.anyio
async def test_product_transport_audit_markdown_renders_stable_summary() -> None:
    scenario = build_product_transport_consistency_scenarios_v1()[0]
    report = await evaluate_product_transport_audit_report(
        scenarios=(scenario,),
        rest_runner=lambda _: {"status": "ok", "result": {"object_id": "obj-1"}},
        mcp_runner=lambda _: {"status": "ok", "result": {"object_id": "obj-2"}},
        cli_runner=lambda _: {"status": "ok", "result": {"candidates": []}},
    )

    markdown = render_product_transport_audit_markdown(
        report,
        title="Product Transport Audit Report",
    )

    assert markdown.startswith("# Product Transport Audit Report\n")
    assert "| Scenario | Command Family | REST | MCP | CLI | REST/MCP | REST/CLI | Failure Reasons |" in markdown
    assert "Failing scenarios:" in markdown
    assert "rest_cli_mismatch" in markdown


@pytest.mark.anyio
async def test_product_transport_audit_markdown_is_written_to_disk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MIND_API_KEY", "test-api-key")
    rest_path = tmp_path / "transport-audit-md-rest.sqlite3"
    mcp_path = tmp_path / "transport-audit-md-mcp.sqlite3"
    cli_path = tmp_path / "transport-audit-md-cli.sqlite3"
    _seed_backend(rest_path)
    _seed_backend(mcp_path)
    _seed_backend(cli_path)

    async with _rest_client(_sqlite_config(rest_path)) as rest_client:
        with create_mcp_server(_sqlite_config(mcp_path)) as mcp_server:
            report = await evaluate_product_transport_audit_report(
                rest_runner=lambda scenario: _run_rest(rest_client, scenario),
                mcp_runner=lambda scenario: _run_mcp(mcp_server, scenario),
                cli_runner=lambda scenario: _run_cli(cli_path, scenario),
            )

    output_path = write_product_transport_audit_markdown(
        tmp_path / "product_transport_audit.md",
        report,
    )

    markdown = output_path.read_text(encoding="utf-8")
    assert output_path.exists()
    assert markdown.startswith("# Product Transport Audit Report\n")
    assert "- Status: `PASS`" in markdown


def test_product_transport_report_main_prints_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_path = tmp_path / "product_transport_audit.json"
    markdown_output_path = tmp_path / "product_transport_audit.md"

    exit_code = product_transport_report_main(
        [
            "--output",
            str(output_path),
            "--markdown-output",
            str(markdown_output_path),
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
    assert markdown_output_path.exists()
    output = capsys.readouterr().out
    assert "Product transport audit report" in output
    assert f"markdown_path={markdown_output_path}" in output
    assert "scenario_count=3" in output
    assert "product_transport_report=PASS" in output


async def _run_rest(
    client: httpx.AsyncClient,
    scenario: Any,
) -> dict[str, Any] | None:
    response = await client.request(
        scenario.rest_method,
        scenario.rest_path,
        headers={"X-API-Key": "test-api-key"},
        json=scenario.rest_json_body,
    )
    if response.status_code != 200:
        return None
    return response.json()


def _run_mcp(server: Any, scenario: Any) -> dict[str, Any] | None:
    if scenario.mcp_tool_name is None:
        return None
    return server.invoke_tool(
        scenario.mcp_tool_name,
        dict(scenario.mcp_args),
        client_info={
            "client_id": "transport-audit",
            "tenant_id": "default",
            "conversation_id": "transport-audit-conv",
            "device_id": "local",
        },
    )


def _run_cli(path: Path, scenario: Any) -> dict[str, Any] | None:
    if scenario.cli_argv is None:
        return None
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = product_main(["--json", "--sqlite-path", str(path), *scenario.cli_argv[1:]])
    if exit_code != 0:
        return None
    output = stdout.getvalue() or stderr.getvalue()
    return json.loads(output)


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


def _sqlite_config(path: Path) -> ResolvedCliConfig:
    return resolve_cli_config(backend="sqlite", sqlite_path=str(path))


def _seed_backend(path: Path) -> None:
    with build_app_registry(_sqlite_config(path)) as registry:
        client = LocalProductClient(registry)
        client.open_session(
            {
                "principal_id": "cli-user",
                "session_id": "session-1",
                "conversation_id": "conv-1",
                "channel": "cli",
                "client_id": "mind-cli",
            }
        )
        client.remember(
            {
                "content": "seed alpha",
                "episode_id": "ep-1",
                "timestamp_order": 1,
                "principal_id": "cli-user",
                "session_id": "session-1",
            }
        )
        client.remember(
            {
                "content": "seed beta",
                "episode_id": "ep-2",
                "timestamp_order": 1,
                "principal_id": "cli-user",
                "session_id": "session-1",
            }
        )
