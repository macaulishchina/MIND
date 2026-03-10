"""WP-6 product CLI verification tests."""

from __future__ import annotations

import io
import json
import tomllib
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from mind.api.client import MindAPIClient
from mind.app.registry import build_app_registry
from mind.cli_config import ResolvedCliConfig, resolve_cli_config
from mind.fixtures import build_product_cli_bench_v1, build_user_state_scenarios_v1
from mind.product_cli import LocalProductClient, build_product_parser, product_main

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
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = product_main(argv)
    output = stdout.getvalue() or stderr.getvalue()
    return exit_code, json.loads(output)


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
        return {"status": payload["status"], "result_keys": sorted(result.keys())}
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
            "backend": result.get("backend"),
            "profile": result.get("profile"),
        }
    return payload
