"""WP-6 product CLI verification tests."""

from __future__ import annotations

import importlib
import io
import json
import sys
import tomllib
from argparse import Namespace
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import httpx
import pytest

from mind.api.app import create_app
from mind.api.client import MindAPIClient
from mind.app.registry import build_app_registry
from mind.cli_config import ResolvedCliConfig, resolve_cli_config
from mind.fixtures import (
    build_product_cli_bench_v1,
    build_product_transport_consistency_scenarios_v1,
    build_user_state_scenarios_v1,
    normalize_product_transport_payload,
)
from mind.product_cli import (
    LocalProductClient,
    _default_episode_id,
    _dispatch_command,
    _merge_shell_args,
    _run_interactive_shell,
    build_product_parser,
    product_main,
)

ROOT = Path(__file__).resolve().parent.parent


def test_product_cli_help_lists_all_7_commands(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_product_parser()

    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["-h"])

    assert excinfo.value.code == 0
    output = capsys.readouterr().out
    for command in ("remember", "recall", "ask", "history", "session", "status", "config"):
        assert command in output


def test_product_cli_help_excludes_dev_commands(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_product_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["-h"])

    output = capsys.readouterr().out
    for command in ("primitive", "access", "governance", "demo", "gate", "report", "offline"):
        assert command not in output


def test_product_cli_supports_json_flag() -> None:
    parser = build_product_parser()

    args = parser.parse_args(["--json", "status"])

    assert args.json is True
    assert args.command == "status"


def test_product_cli_supports_color_flag() -> None:
    parser = build_product_parser()

    args = parser.parse_args(["--color", "always", "status"])

    assert args.color == "always"
    assert args.command == "status"


def test_product_cli_config_supports_provider_preview_flags() -> None:
    parser = build_product_parser()

    args = parser.parse_args(
        [
            "config",
            "--provider",
            "openai",
            "--model",
            "gpt-4.1-mini",
            "--endpoint",
            "https://api.openai.com/v1/responses",
            "--timeout-ms",
            "12000",
            "--retry-policy",
            "none",
        ]
    )

    assert args.command == "config"
    assert args.provider == "openai"
    assert args.model == "gpt-4.1-mini"
    assert args.endpoint == "https://api.openai.com/v1/responses"
    assert args.timeout_ms == 12000
    assert args.retry_policy == "none"


def test_pyproject_points_mind_to_product_cli_and_removes_deprecated_aliases() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = data["project"]["scripts"]

    assert scripts["mind"] == "mind.product_cli:product_main"
    assert "mind-phase-b-gate" not in scripts
    assert "mind-postgres-regression" not in scripts
    assert "mind-offline-worker-once" not in scripts


def test_mind_api_client_serializes_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _FakeResponse:
        def __enter__(self) -> _FakeResponse:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"status":"ok","result":{"saved":true}}'

    def fake_urlopen(request: object, timeout: int) -> _FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr("mind.api.client.urlopen", fake_urlopen)
    client = MindAPIClient("http://example.test/api", api_key="secret")

    response = client.remember({"content": "hello", "episode_id": "ep-1"})

    request = captured["request"]
    assert request.full_url == "http://example.test/api/v1/memories"
    assert request.get_method() == "POST"
    assert request.headers["X-api-key"] == "secret"
    assert json.loads(request.data.decode("utf-8"))["content"] == "hello"
    assert response["status"] == "ok"


def test_mind_api_client_provider_status_serializes_resolve_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _FakeResponse:
        def __enter__(self) -> _FakeResponse:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"status":"ok","result":{"provider":"openai"}}'

    def fake_urlopen(request: object, timeout: int) -> _FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr("mind.api.client.urlopen", fake_urlopen)
    client = MindAPIClient("http://example.test/api", api_key="secret")

    response = client.provider_status(
        {
            "provider_selection": {
                "provider": "openai",
                "model": "gpt-4.1-mini",
            }
        }
    )

    request = captured["request"]
    assert request.full_url == "http://example.test/api/v1/system/provider-status:resolve"
    assert request.get_method() == "POST"
    assert request.headers["X-api-key"] == "secret"
    assert json.loads(request.data.decode("utf-8"))["provider_selection"]["provider"] == "openai"
    assert response["result"]["provider"] == "openai"


def test_mind_api_package_does_not_eagerly_import_server_module() -> None:
    sys.modules.pop("mind.api", None)
    sys.modules.pop("mind.api.app", None)

    api_module = importlib.import_module("mind.api")

    assert api_module.MindAPIClient is MindAPIClient
    assert "mind.api.app" not in sys.modules
    assert callable(api_module.create_app)
    assert "mind.api.app" in sys.modules


def test_product_cli_rejects_sqlite_outside_test_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MIND_ALLOW_SQLITE_FOR_TESTS", raising=False)

    with pytest.raises(SystemExit, match="SQLite is test-only"):
        product_main(["--sqlite-path", str(tmp_path / "forbidden.sqlite3"), "status"])


def test_product_cli_experience_bench_v1(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "product-cli-bench.sqlite3"
    _seed_cli_backend(sqlite_path)
    scenarios = build_product_cli_bench_v1()
    passed = 0

    for scenario in scenarios:
        if _run_bench_scenario(sqlite_path=sqlite_path, argv=scenario.argv):
            passed += 1

    assert len(scenarios) == 30
    assert passed / len(scenarios) >= 0.95


def test_local_vs_remote_cli_behavior_consistency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_path = tmp_path / "product-cli-local.sqlite3"
    remote_path = tmp_path / "product-cli-remote.sqlite3"
    _seed_cli_backend(local_path)
    _seed_cli_backend(remote_path)

    with build_app_registry(_sqlite_config(remote_path)) as registry:
        remote_delegate = LocalProductClient(registry)
        monkeypatch.setattr(
            "mind.product_cli.MindAPIClient",
            lambda base_url, api_key=None: remote_delegate,
        )

        comparable_commands = [
            ["remember", "compare remember", "--episode-id", "cmp-ep-1"],
            ["recall", "seed"],
            ["ask", "seed"],
            ["history", "--limit", "5"],
            [
                "session",
                "open",
                "--principal-id",
                "cli-user",
                "--session-id",
                "session-remote-1",
            ],
            ["session", "list", "--principal-id", "cli-user"],
            ["session", "show", "session-1"],
            ["status"],
            ["config"],
        ]

        matches = 0
        for command in comparable_commands:
            local_code, local_payload = _run_product_cli(
                ["--sqlite-path", str(local_path), *command]
            )
            remote_code, remote_payload = _run_product_cli(
                ["--remote", "http://mind.example", "--api-key", "secret", *command]
            )
            if (
                local_code == 0
                and remote_code == 0
                and _normalize_cli_payload(command[0], local_payload)
                == _normalize_cli_payload(command[0], remote_payload)
            ):
                matches += 1

    assert matches / len(comparable_commands) >= 0.95


@pytest.mark.anyio
async def test_product_transport_consistency_scenarios_v1_rest_cli_pass_rate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MIND_API_KEY", "test-api-key")
    rest_path = tmp_path / "transport-rest-cli.sqlite3"
    cli_path = tmp_path / "transport-cli.sqlite3"
    _seed_cli_backend(rest_path)
    _seed_cli_backend(cli_path)
    scenarios = [
        scenario
        for scenario in build_product_transport_consistency_scenarios_v1()
        if scenario.cli_argv is not None
    ]
    matches = 0

    async with _rest_client(_sqlite_config(rest_path)) as rest_client:
        for scenario in scenarios:
            rest_response = await rest_client.request(
                scenario.rest_method,
                scenario.rest_path,
                headers={"X-API-Key": "test-api-key"},
                json=scenario.rest_json_body,
            )
            if rest_response.status_code != 200:
                continue
            assert scenario.cli_argv is not None
            exit_code, cli_payload = _run_product_cli(
                ["--sqlite-path", str(cli_path), *scenario.cli_argv[1:]]
            )
            if exit_code != 0:
                continue
            if normalize_product_transport_payload(
                scenario.command_family,
                rest_response.json(),
            ) == normalize_product_transport_payload(
                scenario.command_family,
                cli_payload,
            ):
                matches += 1

    assert len(scenarios) >= 3
    assert matches / len(scenarios) >= 0.95


def test_product_cli_status_default_output_is_human_readable(tmp_path: Path) -> None:
    exit_code, output = _run_product_cli_text(
        ["--sqlite-path", str(tmp_path / "status.sqlite3"), "status"]
    )

    assert exit_code == 0
    assert "System Status [OK]" in output
    assert "Health" in output
    assert "Checks" in output
    assert "{" not in output


def test_product_cli_config_json_includes_provider_section(tmp_path: Path) -> None:
    exit_code, payload = _run_product_cli(
        [
            "--sqlite-path",
            str(tmp_path / "config.sqlite3"),
            "config",
            "--provider",
            "openai",
            "--model",
            "gpt-4.1-mini",
        ]
    )

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["result"]["runtime"]["backend"] == "sqlite"
    assert payload["result"]["provider"]["provider"] == "openai"
    assert payload["result"]["provider"]["model"] == "gpt-4.1-mini"


def test_product_cli_remember_default_output_is_human_readable(tmp_path: Path) -> None:
    exit_code, output = _run_product_cli_text(
        [
            "--sqlite-path",
            str(tmp_path / "remember.sqlite3"),
            "remember",
            "hello formatter",
            "--episode-id",
            "fmt-1",
        ]
    )

    assert exit_code == 0
    assert "Stored Memory [OK]" in output
    assert "Object ID" in output
    assert "Provenance ID" in output
    assert "{" not in output


def test_product_cli_recall_shows_object_type_column(tmp_path: Path) -> None:
    store_path = tmp_path / "recall-type.sqlite3"
    _seed_cli_backend(store_path)

    exit_code, output = _run_product_cli_text(
        ["--color", "never", "--sqlite-path", str(store_path), "recall", "seed"]
    )

    assert exit_code == 0
    assert "Candidates" in output
    assert "Type" in output
    assert "RawRecord" in output


def test_product_cli_ask_shows_access_depth_and_object_details(tmp_path: Path) -> None:
    store_path = tmp_path / "ask-details.sqlite3"
    _seed_cli_backend(store_path)

    exit_code, output = _run_product_cli_text(
        ["--color", "never", "--sqlite-path", str(store_path), "ask", "seed"]
    )

    assert exit_code == 0
    assert "Access Depth" in output
    assert "Answer" in output
    assert "focus" in output
    assert "Selected Objects" in output
    assert "Episode" in output
    assert "Preview" in output
    assert output.index("Object ID") < output.index("Type")


def test_product_cli_color_always_emits_ansi_sequences(tmp_path: Path) -> None:
    exit_code, output = _run_product_cli_text(
        [
            "--color",
            "always",
            "--sqlite-path",
            str(tmp_path / "status-color.sqlite3"),
            "status",
        ]
    )

    assert exit_code == 0
    assert "\x1b[" in output


def test_product_cli_remember_episode_id_is_optional() -> None:
    parser = build_product_parser()

    args = parser.parse_args(["remember", "hello world"])

    assert args.command == "remember"
    assert args.content == "hello world"
    assert args.episode_id is None


def test_product_cli_dispatch_generates_default_episode_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mind.product_cli._default_episode_id", lambda: "user-host-window")

    captured: dict[str, Any] = {}

    class _FakeClient:
        def remember(self, payload: dict[str, Any]) -> dict[str, Any]:
            captured["payload"] = payload
            return {"status": "ok", "result": payload}

    args = Namespace(
        command="remember",
        content="hello world",
        episode_id=None,
        timestamp_order=1,
        principal_id="cli-user",
        session_id=None,
        conversation_id=None,
    )

    payload = _dispatch_command(args, _FakeClient())  # type: ignore[arg-type]

    assert captured["payload"]["episode_id"] == "user-host-window"
    assert payload["result"]["episode_id"] == "user-host-window"


def test_default_episode_id_uses_username_hostname_and_window_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mind.product_cli.getpass.getuser", lambda: "Alice")
    monkeypatch.setattr("mind.product_cli.socket.gethostname", lambda: "devbox.local")
    monkeypatch.setenv("TERM_SESSION_ID", "Tab 7")

    assert _default_episode_id() == "alice-devbox-local-tab-7"


def test_interactive_shell_executes_commands_and_reuses_session_defaults(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = build_product_parser()
    session_args = parser.parse_args(["--json"])
    seen: list[dict[str, Any]] = []

    class _FakeClient:
        def health(self) -> dict[str, Any]:
            return {"status": "ok", "result": {"store": "connected"}}

        def remember(self, payload: dict[str, Any]) -> dict[str, Any]:
            seen.append(payload)
            return {"status": "ok", "result": {"object_id": "obj-1"}}

    class _FakeContext:
        def __enter__(self) -> _FakeClient:
            return _FakeClient()

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    inputs = iter(['remember "hello shell"', "exit"])
    monkeypatch.setattr("mind.product_cli._client_context", lambda args: _FakeContext())
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr("mind.product_cli._default_episode_id", lambda: "auto-ep")

    exit_code = _run_interactive_shell(session_args, parser)

    assert exit_code == 0
    assert seen[0]["episode_id"] == "auto-ep"
    out = capsys.readouterr().out
    assert "Connected to local-postgres" in out
    assert '"status": "ok"' in out


def test_merge_shell_args_preserves_session_transport_defaults() -> None:
    session_args = Namespace(
        local=False,
        remote=None,
        api_key="secret",
        json=True,
        profile="postgres_main",
        backend="postgresql",
        postgres_dsn="postgresql+psycopg://postgres:postgres@127.0.0.1:5432/mind",
        sqlite_path=None,
    )
    shell_args = Namespace(
        local=False,
        remote=None,
        api_key=None,
        json=False,
        profile=None,
        backend=None,
        postgres_dsn=None,
        sqlite_path=None,
        command="status",
    )

    merged = _merge_shell_args(session_args, shell_args)

    assert merged.api_key == "secret"
    assert merged.json is True
    assert merged.profile == "postgres_main"
    assert merged.backend == "postgresql"
    assert merged.postgres_dsn == session_args.postgres_dsn


def test_user_state_scenario_fixture_set_is_complete() -> None:
    scenarios = build_user_state_scenarios_v1()

    assert len(scenarios) == 30
    assert scenarios[0].scenario_id == "user-state-01"
    assert scenarios[-1].scenario_id == "user-state-30"


def _run_bench_scenario(*, sqlite_path: Path, argv: tuple[str, ...]) -> bool:
    if "-h" in argv:
        parser = build_product_parser()
        buffer = io.StringIO()
        with pytest.raises(SystemExit) as excinfo:
            with redirect_stdout(buffer):
                parser.parse_args(list(argv[1:]))
        return excinfo.value.code == 0 and bool(buffer.getvalue().strip())

    exit_code, payload = _run_product_cli(["--sqlite-path", str(sqlite_path), *argv[1:]])
    return exit_code == 0 and payload.get("status") == "ok"


def _run_product_cli(argv: list[str]) -> tuple[int, dict[str, Any]]:
    return _run_product_cli_json(argv)


def _run_product_cli_json(argv: list[str]) -> tuple[int, dict[str, Any]]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = product_main(["--json", *argv])
    output = stdout.getvalue() or stderr.getvalue()
    return exit_code, json.loads(output)


def _run_product_cli_text(argv: list[str]) -> tuple[int, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = product_main(argv)
    output = stdout.getvalue() or stderr.getvalue()
    return exit_code, output


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


def _seed_cli_backend(path: Path) -> None:
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


def _normalize_cli_payload(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    if command == "remember":
        result = payload["result"]
        return {"status": payload["status"], "result_keys": sorted(result.keys())}
    if command == "recall":
        result = payload["result"]
        candidate_types = tuple(
            candidate.get("object_type") for candidate in result.get("candidates", [])
        )
        return {
            "status": payload["status"],
            "result_keys": sorted(result.keys()),
            "candidate_types": candidate_types,
        }
    if command == "ask":
        result = payload["result"]
        return {
            "status": payload["status"],
            "result_keys": sorted(result.keys()),
            "selected_mode": result.get("selected_mode"),
        }
    if command == "history":
        result = payload["result"]
        return {"status": payload["status"], "total": result["total"]}
    if command == "session":
        result = payload["result"]
        if isinstance(result, dict) and "sessions" in result:
            return {"status": payload["status"], "total": result["total"]}
        if isinstance(result, dict) and "session_id" in result:
            return {
                "status": payload["status"],
                "session_id": result["session_id"],
                "principal_id": result["principal_id"],
            }
    if command == "status":
        result = payload["result"]
        return {
            "status": payload["status"],
            "health": result["health"]["status"],
            "ready": result["readiness"]["ready"],
        }
    if command == "config":
        result = payload["result"]
        return {
            "status": payload["status"],
            "backend": (result.get("runtime") or {}).get("backend"),
            "profile": (result.get("runtime") or {}).get("profile"),
            "provider": (result.get("provider") or {}).get("provider"),
        }
    return payload
