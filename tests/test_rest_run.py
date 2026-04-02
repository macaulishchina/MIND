"""Tests for the REST launcher CLI."""

from __future__ import annotations

from pathlib import Path

from mind.config import ConfigManager
from mind.interfaces.rest import run as rest_run


def test_rest_run_accepts_explicit_toml_path(tmp_path, monkeypatch):
    toml_path = tmp_path / "rest-smoke.toml"
    toml_path.write_text(
        "\n".join(
            [
                "[rest]",
                'host = "127.0.0.1"',
                "port = 19000",
            ]
        ),
        encoding="utf-8",
    )

    observed: dict[str, object] = {}

    def fake_uvicorn_run(app, host, port):
        observed["app"] = app
        observed["host"] = host
        observed["port"] = port

    monkeypatch.setattr(rest_run.uvicorn, "run", fake_uvicorn_run)

    rest_run.main(["--toml", str(toml_path)])

    assert observed["host"] == "127.0.0.1"
    assert observed["port"] == 19000
    assert observed["app"] is not None


def test_rest_run_parse_args_defaults_to_repo_config():
    args = rest_run.parse_args([])
    assert args.toml_path is None
    assert args.compose_adapt is False


def test_rest_run_parse_args_accepts_compose_adapt():
    args = rest_run.parse_args(["--compose-adapt"])
    assert args.compose_adapt is True


def test_adapt_compose_runtime_config_rewrites_loopback_services():
    config = ConfigManager.from_dict(
        {
            "llm": {
                "provider": "fake",
                "fake": {
                    "protocols": "fake",
                    "model": "fake-memory-test",
                },
            },
            "vector_store": {
                "provider": "pgvector",
                "dsn": "postgresql://postgres:postgres@localhost:5432/mind",
            },
            "history_store": {
                "provider": "postgres",
                "dsn": "postgresql://postgres:postgres@127.0.0.1:5432/mind",
            },
            "stl_store": {
                "provider": "postgres",
                "dsn": "postgresql://postgres:postgres@localhost:5432/mind",
            },
            "rest": {
                "host": "127.0.0.1",
                "port": 8000,
            },
        }
    ).get()

    adapted = rest_run.adapt_compose_runtime_config(config)

    assert adapted.rest.host == "0.0.0.0"
    assert adapted.vector_store.dsn == "postgresql://postgres:postgres@postgres:5432/mind"
    assert adapted.history_store.dsn == "postgresql://postgres:postgres@postgres:5432/mind"
    assert adapted.stl_store.dsn == "postgresql://postgres:postgres@postgres:5432/mind"
