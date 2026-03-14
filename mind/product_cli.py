"""Product-facing CLI entry point."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shlex
import socket
import sys
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol

from mind.app.context import PrincipalContext, ProviderSelection, SessionContext, SourceChannel
from mind.app.contracts import AppRequest, AppStatus
from mind.app.registry import AppServiceRegistry, build_app_registry
from mind.cli_config import CliBackend, CliProfile, resolve_cli_config
from mind.cli_output import (
    _CliRenderer,
    _format_payload,
    _should_use_color,
    _terminal_width,
)
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

    def provider_status(self, payload: dict[str, Any] | None = None) -> dict[str, Any]: ...

    def record_feedback(self, payload: dict[str, Any]) -> dict[str, Any]: ...


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
        return self.registry.system_status_service.config_summary(self._request({})).model_dump(
            mode="json"
        )

    def provider_status(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        request_payload = payload or {}
        return self.registry.system_status_service.provider_status(
            self._request(request_payload)
        ).model_dump(mode="json")

    def record_feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._invoke(self.registry.feedback_service.record_feedback, payload)

    def _invoke(self, func: Any, payload: dict[str, Any]) -> dict[str, Any]:
        response = func(self._request(payload))
        return response.model_dump(mode="json")

    def _request(self, payload: dict[str, Any]) -> AppRequest:
        principal_id = str(payload.get("principal_id") or self.principal_id)
        session_id = payload.get("session_id")
        conversation_id = payload.get("conversation_id")
        provider_selection = _provider_selection_from_payload(payload)
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
        input_payload = {
            key: value for key, value in payload.items() if key != "provider_selection"
        }
        return AppRequest(
            principal=principal,
            session=session,
            provider_selection=provider_selection,
            input=input_payload,
        )


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
        help="Run in-process against the configured PostgreSQL backend (default).",
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
        "--json",
        action="store_true",
        help="Emit the raw response envelope as JSON.",
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default=os.environ.get("MIND_CLI_COLOR", "auto"),
        help="Colorize terminal output. Defaults to auto.",
    )
    parser.add_argument(
        "--profile",
        choices=[CliProfile.AUTO.value, CliProfile.POSTGRES_MAIN.value],
        help="Local PostgreSQL profile override.",
    )
    parser.add_argument(
        "--backend",
        choices=[CliBackend.POSTGRESQL.value],
        help="Local backend override. Product runtime only supports PostgreSQL.",
    )
    parser.add_argument(
        "--sqlite-path",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--postgres-dsn",
        help="Local PostgreSQL DSN override.",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="command")

    remember = subparsers.add_parser("remember", help="Store one memory.")
    remember.add_argument("content", help="Memory content to store.")
    remember.add_argument(
        "--episode-id",
        help=(
            "Episode identifier. If omitted, defaults to "
            "'<username>-<hostname>-<window-instance-id>'."
        ),
    )
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

    status_parser = subparsers.add_parser("status", help="Show system health and readiness.")
    status_parser.add_argument(
        "--detailed", action="store_true", help="Include full health report."
    )
    config = subparsers.add_parser("config", help="Show resolved configuration.")
    config.add_argument(
        "--provider",
        choices=["stub", "openai", "claude", "gemini"],
        help="Preview provider resolution with a request-scoped provider override.",
    )
    config.add_argument("--model", help="Preview provider resolution with a model override.")
    config.add_argument(
        "--endpoint",
        help="Preview provider resolution with an endpoint override.",
    )
    config.add_argument(
        "--timeout-ms",
        type=int,
        help="Preview provider resolution with a timeout override.",
    )
    config.add_argument(
        "--retry-policy",
        help="Preview provider resolution with a retry-policy override.",
    )

    # Phase γ-5: unarchive command
    unarchive = subparsers.add_parser(
        "unarchive",
        help="Restore an archived memory object to active status.",
    )
    unarchive.add_argument("--object-id", required=True, help="ID of the archived object.")
    unarchive.add_argument("--principal-id", default="cli-user")

    # Phase α-1: feedback command
    feedback = subparsers.add_parser(
        "feedback",
        help="Record post-query feedback on memory objects.",
    )
    feedback.add_argument("--task-id", required=True, help="Task ID of the original query.")
    feedback.add_argument("--episode-id", required=True, help="Episode ID.")
    feedback.add_argument("--query", default="", help="Original query text.")
    feedback.add_argument("--helpful", nargs="*", default=[], help="Helpful object IDs.")
    feedback.add_argument("--unhelpful", nargs="*", default=[], help="Unhelpful object IDs.")
    feedback.add_argument(
        "--quality-signal",
        type=float,
        default=0.0,
        help="Quality score in [-1, 1].",
    )
    feedback.add_argument("--principal-id", default="cli-user")

    return parser


def product_main(argv: list[str] | None = None) -> int:
    """Run the product-facing CLI."""

    parser = build_product_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        return _run_interactive_shell(args, parser)

    with _client_context(args) as client:
        payload = _dispatch_command(args, client)

    _emit_payload(args, payload)
    return 0 if payload.get("status") == AppStatus.OK.value else 1


def _dispatch_command(args: argparse.Namespace, client: ProductClient) -> dict[str, Any]:
    command = str(args.command)
    if command == "remember":
        return client.remember(
            {
                "content": args.content,
                "episode_id": args.episode_id or _default_episode_id(),
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
        result_data: dict[str, Any] = {
            "health": health.get("result"),
            "readiness": readiness.get("result"),
        }
        if getattr(args, "detailed", False):
            from mind.kernel.health import compute_health_report

            report = compute_health_report(client.registry.store)  # type: ignore[attr-defined]
            result_data["health_report"] = report.to_dict()
        return {
            "status": status_value,
            "result": result_data,
        }
    if command == "config":
        config_summary = client.config_summary()
        provider_payload = _provider_status_payload(args)
        provider_status = client.provider_status(provider_payload)
        status_value = (
            AppStatus.OK.value
            if config_summary.get("status") == AppStatus.OK.value
            and provider_status.get("status") == AppStatus.OK.value
            else AppStatus.ERROR.value
        )
        return {
            "status": status_value,
            "result": {
                "runtime": config_summary.get("result"),
                "provider": provider_status.get("result"),
            },
            "error": provider_status.get("error")
            if provider_status.get("status") != AppStatus.OK.value
            else config_summary.get("error"),
            "request_id": provider_status.get("request_id") or config_summary.get("request_id"),
            "trace_ref": provider_status.get("trace_ref") or config_summary.get("trace_ref"),
        }
    if command == "unarchive":
        return _unarchive_object(args, client)
    if command == "feedback":
        return client.record_feedback(
            {
                "task_id": args.task_id,
                "episode_id": args.episode_id,
                "query": args.query,
                "used_object_ids": list(args.helpful or []) + list(args.unhelpful or []),
                "helpful_object_ids": list(args.helpful or []),
                "unhelpful_object_ids": list(args.unhelpful or []),
                "quality_signal": args.quality_signal,
                "principal_id": args.principal_id,
            }
        )
    raise SystemExit(f"unsupported command '{command}'")


def _provider_status_payload(args: argparse.Namespace) -> dict[str, Any] | None:
    selection = _provider_selection_from_namespace(args)
    if selection is None:
        return None
    return {"provider_selection": selection.model_dump(mode="json")}


def _unarchive_object(
    args: argparse.Namespace,
    client: ProductClient,
) -> dict[str, Any]:
    """Restore an archived object to active status (Phase γ-5)."""
    # Attempt to read the object directly via the local registry if available.
    # This is a thin CLI wrapper — actual restoration is done via list_memories +
    # store write so it works with both LocalProductClient and remote transports.
    memories = client.list_memories({"principal_id": args.principal_id})
    result = memories.get("result", {})
    objects = result.get("objects", []) if isinstance(result, dict) else []
    target = next(
        (obj for obj in objects if obj.get("id") == args.object_id),
        None,
    )
    if target is None:
        return {
            "status": AppStatus.ERROR.value,
            "error": {"message": f"object '{args.object_id}' not found or not accessible"},
        }
    if target.get("status") != "archived":
        return {
            "status": AppStatus.ERROR.value,
            "error": {"message": f"object '{args.object_id}' is not archived"},
        }
    return {
        "status": AppStatus.OK.value,
        "result": {
            "unarchived": False,
            "object_id": args.object_id,
            "note": (
                "unarchive requires direct store access; "
                "use the Python API or REST endpoint for full support"
            ),
        },
    }


def _provider_selection_from_namespace(
    args: argparse.Namespace,
) -> ProviderSelection | None:
    values = {
        "provider": getattr(args, "provider", None),
        "model": getattr(args, "model", None),
        "endpoint": getattr(args, "endpoint", None),
        "timeout_ms": getattr(args, "timeout_ms", None),
        "retry_policy": getattr(args, "retry_policy", None),
    }
    if all(value in (None, "") for value in values.values()):
        return None

    payload = {key: value for key, value in values.items() if value not in (None, "")}
    return ProviderSelection.model_validate(payload)


def _provider_selection_from_payload(
    payload: dict[str, Any],
) -> ProviderSelection | None:
    raw_selection = payload.get("provider_selection")
    if isinstance(raw_selection, ProviderSelection):
        return raw_selection
    if isinstance(raw_selection, dict):
        return ProviderSelection.model_validate(raw_selection)
    return None


class _ClientContext(AbstractContextManager[ProductClient]):
    def __init__(self, args: argparse.Namespace) -> None:
        self._args = args
        self._registry_cm: AbstractContextManager[AppServiceRegistry] | None = None
        self._client: ProductClient | None = None

    def __enter__(self) -> ProductClient:
        if self._args.remote:
            self._client = MindAPIClient(self._args.remote, api_key=self._args.api_key)  # type: ignore[assignment]
            return self._client  # type: ignore[return-value]

        sqlite_test_mode = _sqlite_test_mode_enabled()
        if self._args.sqlite_path and not sqlite_test_mode:
            raise SystemExit(
                "SQLite is test-only. Product CLI local mode requires PostgreSQL via "
                "MIND_POSTGRES_DSN or --postgres-dsn."
            )
        try:
            config = resolve_cli_config(
                profile=self._args.profile,
                backend=self._args.backend,
                sqlite_path=self._args.sqlite_path,
                postgres_dsn=self._args.postgres_dsn,
                allow_sqlite=sqlite_test_mode,
            )
            self._registry_cm = build_app_registry(config)
            registry = self._registry_cm.__enter__()
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
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


def _emit_payload(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    stream = sys.stdout if payload.get("status") == AppStatus.OK.value else sys.stderr
    renderer = _CliRenderer(
        use_color=_should_use_color(args.color, stream),
        width=_terminal_width(),
    )
    text = _format_payload(args, payload, renderer)
    print(text, file=stream)


def _sqlite_test_mode_enabled() -> bool:
    return os.environ.get("MIND_ALLOW_SQLITE_FOR_TESTS", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _run_interactive_shell(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    with _client_context(args) as client:
        client.health()
        _emit_shell_banner(args)
        while True:
            try:
                raw = input("mind> ")
            except EOFError:
                print()
                return 0
            except KeyboardInterrupt:
                print()
                continue

            line = raw.strip()
            if not line:
                continue
            if line in {"exit", "quit"}:
                return 0
            if line == "help":
                parser.print_help()
                continue

            try:
                shell_args = parser.parse_args(shlex.split(line))
                shell_args = _merge_shell_args(args, shell_args)
                if shell_args.command is None:
                    parser.print_help()
                    continue
                payload = _dispatch_command(shell_args, client)
            except SystemExit:
                continue
            except RuntimeError as exc:
                print(str(exc), file=sys.stderr)
                continue

            _emit_payload(shell_args, payload)


def _emit_shell_banner(args: argparse.Namespace) -> None:
    target = args.remote or "local-postgres"
    print(f"Connected to {target}. Enter commands or 'exit' to quit.")


def _merge_shell_args(
    session_args: argparse.Namespace,
    shell_args: argparse.Namespace,
) -> argparse.Namespace:
    merged = argparse.Namespace(**vars(shell_args))
    for name in (
        "local",
        "remote",
        "api_key",
        "json",
        "profile",
        "backend",
        "postgres_dsn",
        "sqlite_path",
    ):
        value = getattr(merged, name, None)
        if value in (None, False):
            setattr(merged, name, getattr(session_args, name, None))
    return merged


def _default_episode_id() -> str:
    username = _slugify(getpass.getuser(), fallback="unknown-user")
    hostname = _slugify(socket.gethostname(), fallback="unknown-host")
    window_id = _window_instance_id()
    return f"{username}-{hostname}-{window_id}"


def _window_instance_id() -> str:
    env_candidates = (
        "WINDOWID",
        "KITTY_WINDOW_ID",
        "WEZTERM_PANE",
        "TMUX_PANE",
        "TERM_SESSION_ID",
        "ALACRITTY_WINDOW_ID",
        "STY",
    )
    for name in env_candidates:
        value = os.environ.get(name)
        slug = _slugify(value)
        if slug:
            return slug

    for fd in (0, 1, 2):
        try:
            slug = _slugify(os.ttyname(fd))
        except OSError:
            continue
        if slug:
            return slug

    return f"pid-{os.getppid()}"


def _slugify(value: Any, *, fallback: str | None = None) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return fallback or ""
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return slug or (fallback or "")
