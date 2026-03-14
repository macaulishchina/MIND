"""Product transport audit helpers."""

from __future__ import annotations

import asyncio
import inspect
import io
import json
import os
import tempfile
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .product_transport_scenarios import (
    ProductTransportConsistencyScenario,
    build_product_transport_consistency_scenarios_v1,
    normalize_product_transport_payload,
)

_SCHEMA_VERSION = "product_transport_audit_v1"
_BENCH_VERSION = "ProductTransportConsistencyScenarios v1"


@dataclass(frozen=True)
class ProductTransportScenarioAuditResult:
    """Outcome for one shared transport consistency scenario."""

    scenario_id: str
    command_family: str
    rest_available: bool
    mcp_available: bool | None
    cli_available: bool | None
    rest_mcp_match: bool | None
    rest_cli_match: bool | None
    failure_reasons: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failure_reasons


@dataclass(frozen=True)
class ProductTransportAuditReport:
    """Aggregated product transport audit report."""

    schema_version: str
    generated_at: str
    bench_version: str
    scenario_count: int
    passed_count: int
    rest_mcp_pair_count: int
    rest_mcp_match_count: int
    rest_cli_pair_count: int
    rest_cli_match_count: int
    failure_ids: tuple[str, ...]
    scenario_results: tuple[ProductTransportScenarioAuditResult, ...]

    @property
    def coverage(self) -> float:
        if self.scenario_count == 0:
            return 0.0
        return round(self.passed_count / float(self.scenario_count), 4)

    @property
    def rest_mcp_pass_rate(self) -> float:
        if self.rest_mcp_pair_count == 0:
            return 0.0
        return round(self.rest_mcp_match_count / float(self.rest_mcp_pair_count), 4)

    @property
    def rest_cli_pass_rate(self) -> float:
        if self.rest_cli_pair_count == 0:
            return 0.0
        return round(self.rest_cli_match_count / float(self.rest_cli_pair_count), 4)

    @property
    def passed(self) -> bool:
        rest_mcp_ok = self.rest_mcp_pair_count == 0 or self.rest_mcp_pass_rate == 1.0
        rest_cli_ok = self.rest_cli_pair_count == 0 or self.rest_cli_pass_rate == 1.0
        return self.coverage == 1.0 and rest_mcp_ok and rest_cli_ok


async def evaluate_product_transport_audit_report(
    *,
    rest_runner: Callable[[ProductTransportConsistencyScenario], Any],
    mcp_runner: Callable[[ProductTransportConsistencyScenario], Any] | None = None,
    cli_runner: Callable[[ProductTransportConsistencyScenario], Any] | None = None,
    scenarios: tuple[ProductTransportConsistencyScenario, ...] | None = None,
    generated_at: datetime | None = None,
) -> ProductTransportAuditReport:
    """Evaluate shared transport consistency scenarios across REST/MCP/CLI."""

    frozen_scenarios = scenarios or build_product_transport_consistency_scenarios_v1()
    scenario_results: list[ProductTransportScenarioAuditResult] = []

    for scenario in frozen_scenarios:
        rest_payload = await _invoke_runner(rest_runner, scenario)
        rest_normalized = _normalize_payload(scenario, rest_payload)
        failures: list[str] = []
        if rest_normalized is None:
            failures.append("rest_unavailable")

        mcp_available: bool | None = None
        rest_mcp_match: bool | None = None
        if scenario.mcp_tool_name is not None:
            if mcp_runner is None:
                failures.append("mcp_runner_missing")
            else:
                mcp_payload = await _invoke_runner(mcp_runner, scenario)
                mcp_normalized = _normalize_payload(scenario, mcp_payload)
                mcp_available = mcp_normalized is not None
                if not mcp_available:
                    failures.append("mcp_unavailable")
                elif rest_normalized is None:
                    rest_mcp_match = False
                    failures.append("rest_mcp_mismatch")
                else:
                    rest_mcp_match = rest_normalized == mcp_normalized
                    if not rest_mcp_match:
                        failures.append("rest_mcp_mismatch")

        cli_available: bool | None = None
        rest_cli_match: bool | None = None
        if scenario.cli_argv is not None:
            if cli_runner is None:
                failures.append("cli_runner_missing")
            else:
                cli_payload = await _invoke_runner(cli_runner, scenario)
                cli_normalized = _normalize_payload(scenario, cli_payload)
                cli_available = cli_normalized is not None
                if not cli_available:
                    failures.append("cli_unavailable")
                elif rest_normalized is None:
                    rest_cli_match = False
                    failures.append("rest_cli_mismatch")
                else:
                    rest_cli_match = rest_normalized == cli_normalized
                    if not rest_cli_match:
                        failures.append("rest_cli_mismatch")

        scenario_results.append(
            ProductTransportScenarioAuditResult(
                scenario_id=scenario.scenario_id,
                command_family=scenario.command_family,
                rest_available=rest_normalized is not None,
                mcp_available=mcp_available,
                cli_available=cli_available,
                rest_mcp_match=rest_mcp_match,
                rest_cli_match=rest_cli_match,
                failure_reasons=tuple(failures),
            )
        )

    failure_ids = tuple(result.scenario_id for result in scenario_results if not result.passed)
    return ProductTransportAuditReport(
        schema_version=_SCHEMA_VERSION,
        generated_at=(generated_at or datetime.now(UTC)).isoformat(),
        bench_version=_BENCH_VERSION,
        scenario_count=len(scenario_results),
        passed_count=sum(result.passed for result in scenario_results),
        rest_mcp_pair_count=sum(result.rest_mcp_match is not None for result in scenario_results),
        rest_mcp_match_count=sum(result.rest_mcp_match is True for result in scenario_results),
        rest_cli_pair_count=sum(result.rest_cli_match is not None for result in scenario_results),
        rest_cli_match_count=sum(result.rest_cli_match is True for result in scenario_results),
        failure_ids=failure_ids,
        scenario_results=tuple(scenario_results),
    )


def assert_product_transport_audit(
    report: ProductTransportAuditReport,
    *,
    min_pass_rate: float = 0.95,
) -> None:
    """Assert that the transport audit satisfies the required pass rates."""

    if report.coverage < min_pass_rate:
        raise RuntimeError(
            "product transport audit coverage below threshold: "
            f"{report.coverage:.4f} < {min_pass_rate:.4f}"
        )
    if report.rest_mcp_pair_count > 0 and report.rest_mcp_pass_rate < min_pass_rate:
        raise RuntimeError(
            "REST/MCP transport consistency below threshold: "
            f"{report.rest_mcp_pass_rate:.4f} < {min_pass_rate:.4f}"
        )
    if report.rest_cli_pair_count > 0 and report.rest_cli_pass_rate < min_pass_rate:
        raise RuntimeError(
            "REST/CLI transport consistency below threshold: "
            f"{report.rest_cli_pass_rate:.4f} < {min_pass_rate:.4f}"
        )


def evaluate_runtime_product_transport_audit_report(
    *,
    scenarios: tuple[ProductTransportConsistencyScenario, ...] | None = None,
    api_key: str | None = None,
) -> ProductTransportAuditReport:
    """Run the frozen transport audit against the current REST / MCP / CLI stack."""

    return asyncio.run(
        _evaluate_runtime_product_transport_audit_report_async(
            scenarios=scenarios,
            api_key=api_key,
        )
    )


def write_product_transport_audit_json(
    path: str | Path,
    report: ProductTransportAuditReport,
) -> Path:
    """Persist the full product transport audit report as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_report_to_dict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def render_product_transport_audit_markdown(
    report: ProductTransportAuditReport,
    *,
    title: str = "Product Transport Audit Report",
) -> str:
    """Render the product transport audit report as Markdown."""

    lines = [
        f"# {title}",
        "",
        f"- Generated at: `{report.generated_at}`",
        f"- Bench version: `{report.bench_version}`",
        f"- Status: `{'PASS' if report.passed else 'FAIL'}`",
        f"- Coverage: `{report.passed_count}/{report.scenario_count}` (`{report.coverage:.4f}`)",
        f"- REST/MCP pass rate: "
        f"`{report.rest_mcp_match_count}/{report.rest_mcp_pair_count}` "
        f"(`{report.rest_mcp_pass_rate:.4f}`)",
        f"- REST/CLI pass rate: "
        f"`{report.rest_cli_match_count}/{report.rest_cli_pair_count}` "
        f"(`{report.rest_cli_pass_rate:.4f}`)",
        "",
        "| Scenario | Command Family | REST | MCP | CLI | REST/MCP | REST/CLI | Failure Reasons |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in report.scenario_results:
        lines.append(
            "| "
            f"{result.scenario_id} | "
            f"{result.command_family} | "
            f"{_markdown_bool(result.rest_available)} | "
            f"{_markdown_bool(result.mcp_available)} | "
            f"{_markdown_bool(result.cli_available)} | "
            f"{_markdown_bool(result.rest_mcp_match)} | "
            f"{_markdown_bool(result.rest_cli_match)} | "
            f"{','.join(result.failure_reasons) if result.failure_reasons else '-'} |"
        )
    if report.failure_ids:
        lines.extend(
            [
                "",
                f"Failing scenarios: `{','.join(report.failure_ids)}`",
            ]
        )
    return "\n".join(lines) + "\n"


def write_product_transport_audit_markdown(
    path: str | Path,
    report: ProductTransportAuditReport,
    *,
    title: str = "Product Transport Audit Report",
) -> Path:
    """Persist the product transport audit report as Markdown."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_product_transport_audit_markdown(report, title=title),
        encoding="utf-8",
    )
    return output_path


def read_product_transport_audit_json(path: str | Path) -> ProductTransportAuditReport:
    """Load a previously persisted product transport audit report."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError(
            f"unexpected product transport audit schema_version ({payload.get('schema_version')!r})"
        )
    return _report_from_dict(payload)


async def _invoke_runner(
    runner: Callable[[ProductTransportConsistencyScenario], Any],
    scenario: ProductTransportConsistencyScenario,
) -> Any:
    result = runner(scenario)
    if inspect.isawaitable(result):
        return await result
    return result


def _normalize_payload(
    scenario: ProductTransportConsistencyScenario,
    payload: Any,
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("status") != "ok":
        return None
    return normalize_product_transport_payload(scenario.command_family, payload)


async def _evaluate_runtime_product_transport_audit_report_async(
    *,
    scenarios: tuple[ProductTransportConsistencyScenario, ...] | None = None,
    api_key: str | None = None,
) -> ProductTransportAuditReport:
    from mind.api.app import create_app
    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config
    from mind.mcp.server import create_mcp_server
    from mind.product_cli import LocalProductClient, product_main

    previous_api_key = os.environ.get("MIND_API_KEY")
    previous_allow_sqlite = os.environ.get("MIND_ALLOW_SQLITE_FOR_TESTS")
    effective_api_key = api_key or previous_api_key or "mindtest-product-transport"
    os.environ["MIND_API_KEY"] = effective_api_key
    os.environ["MIND_ALLOW_SQLITE_FOR_TESTS"] = "1"

    try:
        with tempfile.TemporaryDirectory(prefix="mind-product-transport-") as tmpdir:
            root = Path(tmpdir)
            rest_path = root / "rest.sqlite3"
            mcp_path = root / "mcp.sqlite3"
            cli_path = root / "cli.sqlite3"
            _seed_runtime_backend(
                rest_path, LocalProductClient, resolve_cli_config, build_app_registry
            )
            _seed_runtime_backend(
                mcp_path, LocalProductClient, resolve_cli_config, build_app_registry
            )
            _seed_runtime_backend(
                cli_path, LocalProductClient, resolve_cli_config, build_app_registry
            )

            rest_config = resolve_cli_config(backend="sqlite", sqlite_path=str(rest_path))
            mcp_config = resolve_cli_config(backend="sqlite", sqlite_path=str(mcp_path))
            frozen_scenarios = scenarios or build_product_transport_consistency_scenarios_v1()

            async with _runtime_rest_client(create_app, rest_config) as rest_client:
                with create_mcp_server(mcp_config) as mcp_server:
                    return await evaluate_product_transport_audit_report(
                        scenarios=frozen_scenarios,
                        rest_runner=lambda scenario: _run_runtime_rest(
                            rest_client,
                            scenario,
                            api_key=effective_api_key,
                        ),
                        mcp_runner=lambda scenario: _run_runtime_mcp(mcp_server, scenario),
                        cli_runner=lambda scenario: _run_runtime_cli(
                            cli_path,
                            scenario,
                            product_main=product_main,
                        ),
                    )
    finally:
        if previous_api_key is None:
            os.environ.pop("MIND_API_KEY", None)
        else:
            os.environ["MIND_API_KEY"] = previous_api_key
        if previous_allow_sqlite is None:
            os.environ.pop("MIND_ALLOW_SQLITE_FOR_TESTS", None)
        else:
            os.environ["MIND_ALLOW_SQLITE_FOR_TESTS"] = previous_allow_sqlite


def _seed_runtime_backend(
    path: Path,
    local_client_type: Any,
    resolve_cli_config: Callable[..., Any],
    build_app_registry: Callable[[Any], Any],
) -> None:
    with build_app_registry(
        resolve_cli_config(backend="sqlite", sqlite_path=str(path))
    ) as registry:
        client = local_client_type(registry)
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


@asynccontextmanager
async def _runtime_rest_client(
    create_app: Callable[[Any], Any],
    config: Any,
) -> AsyncIterator[Any]:
    import httpx

    app = create_app(config)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            yield client


async def _run_runtime_rest(
    client: Any,
    scenario: ProductTransportConsistencyScenario,
    *,
    api_key: str,
) -> dict[str, Any] | None:
    response = await client.request(
        scenario.rest_method,
        scenario.rest_path,
        headers={"X-API-Key": api_key},
        json=scenario.rest_json_body,
    )
    if response.status_code != 200:
        return None
    return response.json()


def _run_runtime_mcp(
    server: Any,
    scenario: ProductTransportConsistencyScenario,
) -> dict[str, Any] | None:
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


def _run_runtime_cli(
    sqlite_path: Path,
    scenario: ProductTransportConsistencyScenario,
    *,
    product_main: Callable[[list[str] | None], int],
) -> dict[str, Any] | None:
    if scenario.cli_argv is None:
        return None
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = product_main(
            ["--json", "--sqlite-path", str(sqlite_path), *scenario.cli_argv[1:]]
        )
    if exit_code != 0:
        return None
    output = stdout.getvalue() or stderr.getvalue()
    return json.loads(output)


def _report_to_dict(report: ProductTransportAuditReport) -> dict[str, Any]:
    return {
        "schema_version": report.schema_version,
        "generated_at": report.generated_at,
        "bench_version": report.bench_version,
        "scenario_count": report.scenario_count,
        "passed_count": report.passed_count,
        "coverage": report.coverage,
        "passed": report.passed,
        "rest_mcp_pair_count": report.rest_mcp_pair_count,
        "rest_mcp_match_count": report.rest_mcp_match_count,
        "rest_mcp_pass_rate": report.rest_mcp_pass_rate,
        "rest_cli_pair_count": report.rest_cli_pair_count,
        "rest_cli_match_count": report.rest_cli_match_count,
        "rest_cli_pass_rate": report.rest_cli_pass_rate,
        "failure_ids": list(report.failure_ids),
        "scenario_results": [
            {
                "scenario_id": result.scenario_id,
                "command_family": result.command_family,
                "rest_available": result.rest_available,
                "mcp_available": result.mcp_available,
                "cli_available": result.cli_available,
                "rest_mcp_match": result.rest_mcp_match,
                "rest_cli_match": result.rest_cli_match,
                "failure_reasons": list(result.failure_reasons),
                "passed": result.passed,
            }
            for result in report.scenario_results
        ],
    }


def _report_from_dict(payload: dict[str, Any]) -> ProductTransportAuditReport:
    return ProductTransportAuditReport(
        schema_version=str(payload["schema_version"]),
        generated_at=str(payload["generated_at"]),
        bench_version=str(payload["bench_version"]),
        scenario_count=int(payload["scenario_count"]),
        passed_count=int(payload["passed_count"]),
        rest_mcp_pair_count=int(payload["rest_mcp_pair_count"]),
        rest_mcp_match_count=int(payload["rest_mcp_match_count"]),
        rest_cli_pair_count=int(payload["rest_cli_pair_count"]),
        rest_cli_match_count=int(payload["rest_cli_match_count"]),
        failure_ids=tuple(payload["failure_ids"]),
        scenario_results=tuple(
            ProductTransportScenarioAuditResult(
                scenario_id=str(result["scenario_id"]),
                command_family=str(result["command_family"]),
                rest_available=bool(result["rest_available"]),
                mcp_available=(
                    bool(result["mcp_available"]) if result["mcp_available"] is not None else None
                ),
                cli_available=(
                    bool(result["cli_available"]) if result["cli_available"] is not None else None
                ),
                rest_mcp_match=(
                    bool(result["rest_mcp_match"]) if result["rest_mcp_match"] is not None else None
                ),
                rest_cli_match=(
                    bool(result["rest_cli_match"]) if result["rest_cli_match"] is not None else None
                ),
                failure_reasons=tuple(result["failure_reasons"]),
            )
            for result in payload["scenario_results"]
        ),
    )


def _markdown_bool(value: bool | None) -> str:
    if value is None:
        return "-"
    return "PASS" if value else "FAIL"
