"""Product-facing CLI entry point."""

from __future__ import annotations

import argparse
import json
import os
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol

from mind.app.context import PrincipalContext, SessionContext, SourceChannel
from mind.app.contracts import AppRequest, AppStatus
from mind.app.registry import AppServiceRegistry, build_app_registry
from mind.cli_config import CliBackend, CliProfile, resolve_cli_config
from mind.primitives.contracts import Capability

from .api.client import MindAPIClient


class ProductClient(Protocol):
    """Transport surface consumed by the product CLI."""

    def remember(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def recall(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def ask(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def list_memories(self, params: dict[str, Any] | None = None) -> dict[str, Any]: ...

    def open_session(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def list_sessions(self, params: dict[str, Any] | None = None) -> dict[str, Any]: ...

    def get_session(self, session_id: str) -> dict[str, Any]: ...

    def health(self) -> dict[str, Any]: ...

    def readiness(self) -> dict[str, Any]: ...

    def config_summary(self) -> dict[str, Any]: ...


@dataclass
class LocalProductClient:
    """Local in-process product transport backed by app services."""

    registry: AppServiceRegistry
    principal_id: str = "cli-user"
    client_id: str = "mind-cli"

    def remember(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._invoke(self.registry.memory_ingest_service.remember, payload)

    def recall(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._invoke(self.registry.memory_query_service.recall, payload)

    def ask(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._invoke(self.registry.memory_access_service.ask, payload)

    def list_memories(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._invoke(self.registry.memory_query_service.list_memories, params or {})

    def open_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._invoke(self.registry.user_state_service.open_session, payload)

    def list_sessions(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._invoke(self.registry.user_state_service.list_sessions, params or {})

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self._invoke(
            self.registry.user_state_service.get_session,
            {"session_id": session_id},
        )

    def health(self) -> dict[str, Any]:
        return self.registry.system_status_service.health(self._request({})).model_dump(mode="json")

    def readiness(self) -> dict[str, Any]:
        return self.registry.system_status_service.readiness(self._request({})).model_dump(
            mode="json"
        )

    def config_summary(self) -> dict[str, Any]:
        return self.registry.system_status_service.config_summary(
            self._request({})
        ).model_dump(mode="json")

    def _invoke(self, func: Any, payload: dict[str, Any]) -> dict[str, Any]:
        response = func(self._request(payload))
        return response.model_dump(mode="json")

    def _request(self, payload: dict[str, Any]) -> AppRequest:
        principal_id = str(payload.get("principal_id") or self.principal_id)
        session_id = payload.get("session_id")
        conversation_id = payload.get("conversation_id")
        principal = PrincipalContext(
            principal_id=principal_id,
            tenant_id=str(payload.get("tenant_id") or "default"),
            capabilities=list(Capability),
        )
        session: SessionContext | None = None
        if session_id is not None or conversation_id is not None:
            session = SessionContext(
                session_id=str(session_id or f"cli-session-{principal_id}"),
                conversation_id=str(conversation_id) if conversation_id is not None else None,
                channel=SourceChannel.CLI,
                client_id=self.client_id,
                device_id=str(payload.get("device_id")) if payload.get("device_id") else None,
            )
        return AppRequest(principal=principal, session=session, input=dict(payload))


def build_product_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the product CLI."""

    parser = argparse.ArgumentParser(
        prog="mind",
        description="Product CLI for MIND memory workflows.",
    )
    transport_group = parser.add_mutually_exclusive_group()
    transport_group.add_argument(
        "--local",
        action="store_true",
        help="Run in-process against the configured backend (default).",
    )
    transport_group.add_argument(
        "--remote",
        help="Base URL for a remote MIND API deployment.",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("MIND_API_KEY"),
        help="API key for --remote mode. Falls back to MIND_API_KEY.",
    )
    parser.add_argument(
        "--profile",
        choices=[profile.value for profile in CliProfile],
        help="Resolved local profile override.",
    )
    parser.add_argument(
        "--backend",
        choices=[backend.value for backend in CliBackend],
        help="Local backend override.",
    )
    parser.add_argument(
        "--sqlite-path",
        help="Local SQLite path override.",
    )
    parser.add_argument(
        "--postgres-dsn",
        help="Local PostgreSQL DSN override.",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="command")

    remember = subparsers.add_parser("remember", help="Store one memory.")
    remember.add_argument("content", help="Memory content to store.")
    remember.add_argument("--episode-id", required=True, help="Episode identifier.")
    remember.add_argument("--timestamp-order", type=int, default=1)
    remember.add_argument("--principal-id", default="cli-user")
    remember.add_argument("--session-id")
    remember.add_argument("--conversation-id")

    recall = subparsers.add_parser("recall", help="Recall memories by query.")
    recall.add_argument("query", help="Recall query.")
    recall.add_argument("--query-mode", action="append", default=["keyword"])
    recall.add_argument("--max-candidates", type=int, default=10)
    recall.add_argument("--principal-id", default="cli-user")
    recall.add_argument("--session-id")

    ask = subparsers.add_parser("ask", help="Ask memory a question.")
    ask.add_argument("query", help="Question to ask against memory.")
    ask.add_argument("--mode", default="auto")
    ask.add_argument("--task-id")
    ask.add_argument("--episode-id")
    ask.add_argument("--principal-id", default="cli-user")
    ask.add_argument("--session-id")

    history = subparsers.add_parser("history", help="List recent memories.")
    history.add_argument("--limit", type=int, default=10)
    history.add_argument("--offset", type=int, default=0)
    history.add_argument("--episode-id")
    history.add_argument("--principal-id", default="cli-user")

    session = subparsers.add_parser("session", help="Manage product sessions.")
    session_subparsers = session.add_subparsers(dest="session_command", metavar="session-command")

    session_open = session_subparsers.add_parser("open", help="Open or update a session.")
    session_open.add_argument("--principal-id", required=True)
    session_open.add_argument("--session-id", required=True)
    session_open.add_argument("--conversation-id")
    session_open.add_argument(
        "--channel",
        choices=[channel.value for channel in SourceChannel],
        default=SourceChannel.CLI.value,
    )
    session_open.add_argument("--client-id", default="mind-cli")
    session_open.add_argument("--device-id")

    session_list = session_subparsers.add_parser("list", help="List sessions.")
    session_list.add_argument("--principal-id")

    session_show = session_subparsers.add_parser("show", help="Show one session.")
    session_show.add_argument("session_id")

    subparsers.add_parser("status", help="Show system health and readiness.")
    subparsers.add_parser("config", help="Show resolved configuration.")

    return parser


def product_main(argv: list[str] | None = None) -> int:
    """Run the product-facing CLI."""

    parser = build_product_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0

    with _client_context(args) as client:
        payload = _dispatch_command(args, client)

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("status") == AppStatus.OK.value else 1


def _dispatch_command(args: argparse.Namespace, client: ProductClient) -> dict[str, Any]:
    command = str(args.command)
    if command == "remember":
        return client.remember(
            {
                "content": args.content,
                "episode_id": args.episode_id,
                "timestamp_order": args.timestamp_order,
                "principal_id": args.principal_id,
                "session_id": args.session_id,
                "conversation_id": args.conversation_id,
            }
        )
    if command == "recall":
        return client.recall(
            {
                "query": args.query,
                "query_modes": args.query_mode,
                "max_candidates": args.max_candidates,
                "principal_id": args.principal_id,
                "session_id": args.session_id,
            }
        )
    if command == "ask":
        return client.ask(
            {
                "query": args.query,
                "mode": args.mode,
                "task_id": args.task_id or f"task-{args.principal_id}",
                "episode_id": args.episode_id,
                "principal_id": args.principal_id,
                "session_id": args.session_id,
            }
        )
    if command == "history":
        return client.list_memories(
            {
                "limit": args.limit,
                "offset": args.offset,
                "episode_id": args.episode_id,
                "principal_id": args.principal_id,
            }
        )
    if command == "session":
        if args.session_command == "open":
            return client.open_session(
                {
                    "principal_id": args.principal_id,
                    "session_id": args.session_id,
                    "conversation_id": args.conversation_id,
                    "channel": args.channel,
                    "client_id": args.client_id,
                    "device_id": args.device_id,
                }
            )
        if args.session_command == "list":
            return client.list_sessions({"principal_id": args.principal_id})
        if args.session_command == "show":
            return client.get_session(args.session_id)
        raise SystemExit("session requires one of: open, list, show")
    if command == "status":
        health = client.health()
        readiness = client.readiness()
        status_value = (
            AppStatus.OK.value
            if health.get("status") == AppStatus.OK.value
            and readiness.get("status") == AppStatus.OK.value
            else AppStatus.ERROR.value
        )
        return {
            "status": status_value,
            "result": {
                "health": health.get("result"),
                "readiness": readiness.get("result"),
            },
        }
    if command == "config":
        return client.config_summary()
    raise SystemExit(f"unsupported command '{command}'")


class _ClientContext(AbstractContextManager[ProductClient]):
    def __init__(self, args: argparse.Namespace) -> None:
        self._args = args
        self._registry_cm: AbstractContextManager[AppServiceRegistry] | None = None
        self._client: ProductClient | None = None

    def __enter__(self) -> ProductClient:
        if self._args.remote:
            self._client = MindAPIClient(self._args.remote, api_key=self._args.api_key)
            return self._client

        config = resolve_cli_config(
            profile=self._args.profile,
            backend=self._args.backend,
            sqlite_path=self._args.sqlite_path,
            postgres_dsn=self._args.postgres_dsn,
        )
        self._registry_cm = build_app_registry(config)
        registry = self._registry_cm.__enter__()
        self._client = LocalProductClient(registry)
        return self._client

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        if self._registry_cm is not None:
            self._registry_cm.__exit__(exc_type, exc, tb)


def _client_context(args: argparse.Namespace) -> _ClientContext:
    return _ClientContext(args)
