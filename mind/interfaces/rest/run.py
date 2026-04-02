"""Launch the maintained REST adapter using resolved config."""

from __future__ import annotations

import argparse
from urllib.parse import quote, urlsplit, urlunsplit
from typing import Optional, Sequence

import uvicorn

from mind.config import ConfigManager
from mind.config.schema import MemoryConfig
from mind.interfaces.rest.app import create_app


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}


def _replace_loopback_host(url: str, replacement_host: str) -> str:
    """Replace loopback hostnames inside a URL/DSN when present."""
    if not url:
        return url

    parsed = urlsplit(url)
    if parsed.hostname not in _LOOPBACK_HOSTS:
        return url

    userinfo = ""
    if parsed.username:
        userinfo = quote(parsed.username, safe="")
        if parsed.password is not None:
            userinfo = f"{userinfo}:{quote(parsed.password, safe='')}"
        userinfo = f"{userinfo}@"

    port = f":{parsed.port}" if parsed.port is not None else ""
    netloc = f"{userinfo}{replacement_host}{port}"
    return urlunsplit(parsed._replace(netloc=netloc))


def adapt_compose_runtime_config(config: MemoryConfig) -> MemoryConfig:
    """Adapt loopback-oriented config values for in-container Compose runtime."""
    adapted = config.model_copy(deep=True)

    if adapted.rest.host in _LOOPBACK_HOSTS:
        adapted.rest.host = "0.0.0.0"

    if adapted.vector_store.provider == "pgvector":
        adapted.vector_store.dsn = _replace_loopback_host(
            adapted.vector_store.dsn,
            "postgres",
        )
    elif adapted.vector_store.provider == "qdrant":
        adapted.vector_store.url = _replace_loopback_host(
            adapted.vector_store.url,
            "qdrant",
        )

    if adapted.history_store.provider == "postgres":
        adapted.history_store.dsn = _replace_loopback_host(
            adapted.history_store.dsn,
            "postgres",
        )

    if adapted.stl_store.provider == "postgres":
        adapted.stl_store.dsn = _replace_loopback_host(
            adapted.stl_store.dsn,
            "postgres",
        )

    return adapted


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the maintained MIND REST adapter.",
    )
    parser.add_argument(
        "--toml",
        dest="toml_path",
        default=None,
        help="Optional TOML config path. Defaults to mind.toml.",
    )
    parser.add_argument(
        "--compose-adapt",
        action="store_true",
        help=(
            "Adapt loopback-oriented TOML values for in-container Compose runtime "
            "(for example localhost -> postgres, 127.0.0.1 -> 0.0.0.0)."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None, toml_path: Optional[str] = None) -> None:
    args = parse_args(argv)
    resolved_toml = toml_path if toml_path is not None else args.toml_path
    config = ConfigManager(toml_path=resolved_toml).get()
    if args.compose_adapt:
        config = adapt_compose_runtime_config(config)
    app = create_app(config=config)
    uvicorn.run(app, host=config.rest.host, port=config.rest.port)


if __name__ == "__main__":
    main()
