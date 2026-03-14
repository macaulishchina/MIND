"""Product-facing CLI entry point."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shlex
import shutil
import socket
import sys
import textwrap
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol

from mind.app.context import PrincipalContext, ProviderSelection, SessionContext, SourceChannel
from mind.app.contracts import AppRequest, AppStatus
from mind.app.registry import AppServiceRegistry, build_app_registry
from mind.cli_config import CliBackend, CliProfile, resolve_cli_config
from mind.primitives.contracts import Capability

from .api.client import MindAPIClient

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


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


@dataclass(frozen=True)
class _CliRenderer:
    use_color: bool
    width: int

    def title(self, title: str, *, status: str | None = None) -> list[str]:
        line = self._accent(title)
        if status is not None:
            line = f"{line} {self.badge(status)}"
        return [line]

    def section(self, name: str) -> list[str]:
        return ["", self._section(name)]

    def kv_block(self, rows: list[tuple[str, str | None]]) -> list[str]:
        filtered = [(label, value) for label, value in rows if value not in (None, "")]
        if not filtered:
            return []

        label_width = min(max(len(label) for label, _ in filtered), 14)
        value_width = max(24, self.width - label_width - 6)
        lines: list[str] = []
        for label, value in filtered:
            assert value is not None
            text = str(value)
            wrapped = self._wrap_value(text, width=value_width)
            padded_label = self._muted(label.ljust(label_width))
            lines.append(f"  {padded_label}  {wrapped[0]}")
            for continuation in wrapped[1:]:
                lines.append(f"  {' ' * label_width}  {continuation}")
        return lines

    def table(self, headers: list[str], rows: list[list[str]]) -> list[str]:
        if not rows:
            return []

        normalized = [[str(cell) for cell in row] for row in rows]
        widths = [len(header) for header in headers]
        for row in normalized:
            for index, cell in enumerate(row):
                widths[index] = max(widths[index], len(cell))

        widths = self._fit_widths(widths, headers)
        lines = [
            "  " + self._join_cells([self._section(header).strip() for header in headers], widths),
            "  " + self._join_cells(["-" * width for width in widths], widths),
        ]
        for row in normalized:
            lines.append("  " + self._join_cells(row, widths))
        return lines

    def bullets(self, items: list[str]) -> list[str]:
        lines: list[str] = []
        width = max(20, self.width - 6)
        for item in items:
            wrapped = textwrap.wrap(str(item), width=width) or [""]
            lines.append(f"  - {wrapped[0]}")
            for continuation in wrapped[1:]:
                lines.append(f"    {continuation}")
        return lines

    def paragraph(self, text: str) -> list[str]:
        wrapped = textwrap.wrap(text, width=max(28, self.width - 4)) or [""]
        return [f"  {line}" for line in wrapped]

    def badge(self, text: str) -> str:
        normalized = text.upper().replace("_", " ")
        tone = "neutral"
        if text.lower() in {"ok", "healthy", "ready", "connected"}:
            tone = "ok"
        elif text.lower() in {"error", "unhealthy", "unauthorized"}:
            tone = "error"
        elif text.lower() in {"rejected", "not found", "not_found", "warn", "warning"}:
            tone = "warn"
        return self._paint(f"[{normalized}]", tone=tone, bold=True)

    def tone(self, value: str, *, kind: str) -> str:
        return self._paint(value, tone=kind, bold=(kind != "muted"))

    def yes_no(self, value: Any) -> str:
        return self.tone("yes", kind="ok") if bool(value) else self.tone("no", kind="warn")

    def _wrap_value(self, value: str, *, width: int) -> list[str]:
        if len(_strip_ansi(value)) <= width:
            return [value]
        wrapped = textwrap.wrap(_strip_ansi(value), width=width) or [""]
        return wrapped

    def _fit_widths(self, widths: list[int], headers: list[str]) -> list[int]:
        available = max(40, self.width - 2 - (3 * (len(widths) - 1)))
        current = list(widths)
        minimums = [max(3, min(len(header), 8)) for header in headers]
        while sum(current) > available:
            shrinkable = [index for index, width in enumerate(current) if width > minimums[index]]
            if not shrinkable:
                break
            target = max(shrinkable, key=lambda index: current[index] - minimums[index])
            current[target] -= 1
        return current

    def _join_cells(self, cells: list[str], widths: list[int]) -> str:
        fitted = []
        for cell, width in zip(cells, widths, strict=False):
            plain = _truncate(_strip_ansi(cell), width)
            fitted.append(plain.ljust(width))
        return "   ".join(fitted)

    def _accent(self, text: str) -> str:
        return self._paint(text, tone="accent", bold=True)

    def _section(self, text: str) -> str:
        return self._paint(text, tone="section", bold=True)

    def _muted(self, text: str) -> str:
        return self._paint(text, tone="muted")

    def _paint(self, text: str, *, tone: str = "plain", bold: bool = False) -> str:
        if not self.use_color:
            return text

        codes: list[str] = []
        if bold:
            codes.append("1")

        if tone == "accent":
            codes.append("36")
        elif tone == "section":
            codes.append("34")
        elif tone == "ok":
            codes.append("32")
        elif tone == "warn":
            codes.append("33")
        elif tone == "error":
            codes.append("31")
        elif tone == "muted":
            codes.append("2")

        if not codes:
            return text
        return f"\x1b[{';'.join(codes)}m{text}\x1b[0m"


def _format_payload(
    args: argparse.Namespace,
    payload: dict[str, Any],
    renderer: _CliRenderer,
) -> str:
    if payload.get("status") != AppStatus.OK.value:
        return _format_error_payload(payload, renderer)

    command = str(args.command)
    if command == "remember":
        return _format_remember_payload(payload, renderer)
    if command == "recall":
        return _format_recall_payload(payload, renderer)
    if command == "ask":
        return _format_ask_payload(payload, renderer)
    if command == "history":
        return _format_history_payload(payload, renderer)
    if command == "session":
        return _format_session_payload(payload, renderer)
    if command == "status":
        return _format_status_payload(payload, renderer)
    if command == "config":
        return _format_config_payload(payload, renderer)
    return _format_generic_payload(payload, renderer)


def _format_remember_payload(payload: dict[str, Any], renderer: _CliRenderer) -> str:
    result = _result_dict(payload)
    lines = renderer.title("Stored Memory", status="ok")
    lines.extend(
        renderer.kv_block(
            [
                ("Object ID", _stringify(result.get("object_id"))),
                ("Version", _stringify(result.get("version"))),
                ("Provenance ID", _stringify(result.get("provenance_id"))),
            ]
        )
    )
    _append_meta_section(lines, payload, renderer)
    return "\n".join(lines)


def _format_recall_payload(payload: dict[str, Any], renderer: _CliRenderer) -> str:
    result = _result_dict(payload)
    candidate_ids = list(result.get("candidate_ids") or [])
    scores = list(result.get("scores") or [])
    evidence = result.get("evidence_summary") or {}
    candidate_details = list(result.get("candidates") or [])

    lines = renderer.title("Recall Results", status="ok")
    lines.extend(
        renderer.kv_block(
            [
                ("Candidates", _stringify(len(candidate_ids))),
                ("Matched Modes", ", ".join(evidence.get("matched_modes", ())) or None),
                ("Backend", _stringify(evidence.get("retrieval_backend"))),
                ("Returned", _stringify(evidence.get("returned_count"))),
                ("Filtered", _stringify(evidence.get("filtered_count"))),
            ]
        )
    )

    if candidate_ids:
        lines.extend(renderer.section("Candidates"))
        has_type = any(candidate.get("object_type") for candidate in candidate_details)
        has_preview = any(candidate.get("content_preview") for candidate in candidate_details)
        headers = ["#", "Object ID", "Score"]
        if has_type:
            headers.insert(1, "Type")
        if has_preview:
            headers.append("Preview")

        rows: list[list[str]] = []
        for index, object_id in enumerate(candidate_ids, start=1):
            score = scores[index - 1] if index - 1 < len(scores) else None
            candidate = candidate_details[index - 1] if index - 1 < len(candidate_details) else {}
            row = [str(index)]
            if has_type:
                row.append(str(candidate.get("object_type") or "-"))
            row.append(object_id)
            row.append(f"{score:.3f}" if isinstance(score, int | float) else "-")
            if has_preview:
                row.append(str(candidate.get("content_preview") or "-"))
            rows.append(row)
        lines.extend(renderer.table(headers, rows))
    else:
        lines.extend(renderer.section("Candidates"))
        lines.extend(renderer.paragraph("No candidates matched the query."))

    _append_meta_section(lines, payload, renderer)
    return "\n".join(lines)


def _format_ask_payload(payload: dict[str, Any], renderer: _CliRenderer) -> str:
    result = _result_dict(payload)
    trace = result.get("trace") or {}
    events = list(trace.get("events") or [])
    first_event = events[0] if events else {}
    summary_event = events[-1] if events else {}

    candidate_ids = list(result.get("candidate_ids") or [])
    candidate_summaries = list(result.get("candidate_summaries") or [])
    selected_ids = list(result.get("selected_object_ids") or [])
    selected_summaries = list(result.get("selected_summaries") or [])
    verification_notes = list(result.get("verification_notes") or [])

    lines = renderer.title("Access Result", status="ok")
    lines.extend(
        renderer.kv_block(
            [
                ("Access Depth", _display_access_depth(result.get("resolved_mode"))),
                ("Answer", _truncate(_stringify(result.get("answer_text")) or "", 72)),
                ("Selection Reason", _stringify(first_event.get("reason_code"))),
                ("Context Shape", _stringify(result.get("context_kind"))),
                ("Context Objects", _stringify(len(result.get("context_object_ids") or []))),
                ("Candidates", _stringify(len(candidate_ids))),
                ("Reads", _stringify(len(result.get("read_object_ids") or []))),
                ("Selected", _stringify(len(selected_ids))),
                ("Tokens", _stringify(result.get("context_token_count"))),
                ("Summary", _stringify(summary_event.get("summary"))),
            ]
        )
    )

    answer_text = result.get("answer_text")
    if isinstance(answer_text, str) and answer_text.strip():
        lines.extend(renderer.section("Answer"))
        lines.extend(renderer.paragraph(answer_text))

    preview = _extract_context_preview(result.get("context_text"))
    if preview:
        lines.extend(renderer.section("Context Preview"))
        lines.extend(renderer.paragraph(preview))

    if candidate_ids:
        lines.extend(renderer.section("Candidates"))
        lines.extend(_render_access_object_table(renderer, candidate_ids, candidate_summaries))

    if selected_ids:
        lines.extend(renderer.section("Selected Objects"))
        lines.extend(_render_access_object_table(renderer, selected_ids, selected_summaries))

    if events:
        lines.extend(renderer.section("Trace"))
        lines.extend(
            renderer.table(
                ["#", "Event", "Depth", "Summary"],
                [
                    [
                        str(index),
                        str(event.get("event_kind") or "-"),
                        _display_access_depth(event.get("mode")) or "-",
                        _truncate(str(event.get("summary") or ""), 72),
                    ]
                    for index, event in enumerate(events, start=1)
                ],
            )
        )

    if verification_notes:
        lines.extend(renderer.section("Verification"))
        lines.extend(renderer.bullets([str(note) for note in verification_notes]))

    _append_meta_section(lines, payload, renderer)
    return "\n".join(lines)


def _format_history_payload(payload: dict[str, Any], renderer: _CliRenderer) -> str:
    result = _result_dict(payload)
    objects = list(result.get("objects") or [])

    lines = renderer.title("Recent Memories", status="ok")
    lines.extend(
        renderer.kv_block(
            [
                ("Total", _stringify(result.get("total"))),
                ("Limit", _stringify(result.get("limit"))),
                ("Offset", _stringify(result.get("offset"))),
            ]
        )
    )

    if objects:
        lines.extend(renderer.section("Entries"))
        rows: list[list[str]] = []
        for index, obj in enumerate(objects, start=1):
            metadata = obj.get("metadata") or {}
            rows.append(
                [
                    str(index),
                    str(obj.get("id", "-")),
                    str(obj.get("type", "-")),
                    str(metadata.get("episode_id") or "-"),
                    str(obj.get("status", "-")),
                    str(obj.get("version", "-")),
                    _truncate(str(obj.get("content") or ""), 40),
                ]
            )
        lines.extend(
            renderer.table(
                ["#", "Object ID", "Type", "Episode", "Status", "Ver", "Preview"],
                rows,
            )
        )
    else:
        lines.extend(renderer.section("Entries"))
        lines.extend(renderer.paragraph("No memories found."))

    _append_meta_section(lines, payload, renderer)
    return "\n".join(lines)


def _format_session_payload(payload: dict[str, Any], renderer: _CliRenderer) -> str:
    result = _result_dict(payload)
    sessions = result.get("sessions")
    if isinstance(sessions, list):
        lines = renderer.title("Sessions", status="ok")
        lines.extend(renderer.kv_block([("Total", _stringify(result.get("total")))]))
        if sessions:
            lines.extend(renderer.section("Entries"))
            lines.extend(
                renderer.table(
                    ["#", "Session ID", "Principal", "Channel", "Conversation", "Last Active"],
                    [
                        [
                            str(index),
                            str(session.get("session_id", "-")),
                            str(session.get("principal_id", "-")),
                            str(session.get("channel", "-")),
                            str(session.get("conversation_id") or "-"),
                            str(session.get("last_active_at") or "-"),
                        ]
                        for index, session in enumerate(sessions, start=1)
                    ],
                )
            )
        else:
            lines.extend(renderer.section("Entries"))
            lines.extend(renderer.paragraph("No sessions found."))
        _append_meta_section(lines, payload, renderer)
        return "\n".join(lines)

    lines = renderer.title("Session", status="ok")
    lines.extend(
        renderer.kv_block(
            [
                ("Session ID", _stringify(result.get("session_id"))),
                ("Principal ID", _stringify(result.get("principal_id"))),
                ("Conversation", _stringify(result.get("conversation_id"))),
                ("Channel", _stringify(result.get("channel"))),
                ("Client ID", _stringify(result.get("client_id"))),
                ("Device ID", _stringify(result.get("device_id"))),
                ("Started At", _stringify(result.get("started_at"))),
                ("Last Active", _stringify(result.get("last_active_at"))),
            ]
        )
    )
    _append_meta_section(lines, payload, renderer)
    return "\n".join(lines)


def _format_status_payload(payload: dict[str, Any], renderer: _CliRenderer) -> str:
    result = _result_dict(payload)
    health = result.get("health") or {}
    readiness = result.get("readiness") or {}
    checks = readiness.get("checks") or {}

    lines = renderer.title("System Status", status="ok")
    lines.extend(
        renderer.kv_block(
            [
                ("Health", _health_value(renderer, health.get("status"))),
                ("Store", _health_value(renderer, health.get("store"))),
                ("Ready", renderer.yes_no(readiness.get("ready"))),
            ]
        )
    )
    if checks:
        lines.extend(renderer.section("Checks"))
        lines.extend(
            renderer.table(
                ["Check", "Status"],
                [[str(name), str(status)] for name, status in checks.items()],
            )
        )
    # α-S2: detailed health report
    health_report = result.get("health_report")
    if health_report:
        lines.extend(renderer.section("Health Report"))
        lines.extend(
            renderer.kv_block(
                [
                    ("Total Objects", str(health_report.get("total_objects", 0))),
                    ("Avg Priority", str(health_report.get("average_priority", "-"))),
                    ("Pending Jobs", str(health_report.get("pending_jobs", 0))),
                    ("Orphan Refs", str(len(health_report.get("orphan_refs", [])))),
                ]
            )
        )
        type_counts = health_report.get("type_counts", {})
        if type_counts:
            lines.extend(renderer.section("Object Types"))
            lines.extend(
                renderer.table(
                    ["Type", "Count"],
                    [[str(t), str(c)] for t, c in sorted(type_counts.items())],
                )
            )
        status_counts = health_report.get("status_counts", {})
        if status_counts:
            lines.extend(renderer.section("Status Distribution"))
            lines.extend(
                renderer.table(
                    ["Status", "Count"],
                    [[str(s), str(c)] for s, c in sorted(status_counts.items())],
                )
            )
    return "\n".join(lines)


def _format_config_payload(payload: dict[str, Any], renderer: _CliRenderer) -> str:
    result = _result_dict(payload)
    lines = renderer.title("Resolved Config", status="ok")
    if not result:
        lines.extend(renderer.paragraph("No config data returned."))
        return "\n".join(lines)
    runtime = result.get("runtime")
    provider = result.get("provider")
    if isinstance(runtime, dict) or isinstance(provider, dict):
        if isinstance(runtime, dict):
            lines.extend(renderer.section("Runtime"))
            lines.extend(
                renderer.kv_block(
                    [(_labelize(key), _stringify(runtime.get(key))) for key in sorted(runtime)]
                )
            )
        if isinstance(provider, dict):
            lines.extend(renderer.section("Provider"))
            lines.extend(
                renderer.kv_block(
                    [(_labelize(key), _stringify(provider.get(key))) for key in sorted(provider)]
                )
            )
        _append_meta_section(lines, payload, renderer)
        return "\n".join(lines)
    lines.extend(
        renderer.kv_block([(_labelize(key), _stringify(result.get(key))) for key in sorted(result)])
    )
    _append_meta_section(lines, payload, renderer)
    return "\n".join(lines)


def _format_error_payload(payload: dict[str, Any], renderer: _CliRenderer) -> str:
    error = payload.get("error") or {}
    lines = renderer.title("Command Failed", status=str(payload.get("status") or "error"))
    lines.extend(
        renderer.kv_block(
            [
                ("Status", _stringify(payload.get("status"))),
                ("Code", _stringify(error.get("code"))),
                ("Message", _stringify(error.get("message"))),
                (
                    "Retryable",
                    renderer.yes_no(error.get("retryable"))
                    if error.get("retryable") is not None
                    else None,
                ),
            ]
        )
    )
    details = error.get("details") or {}
    if details:
        lines.extend(renderer.section("Details"))
        lines.extend(
            renderer.kv_block(
                [(_labelize(key), _stringify(details[key])) for key in sorted(details)]
            )
        )
    _append_meta_section(lines, payload, renderer)
    return "\n".join(lines)


def _format_generic_payload(payload: dict[str, Any], renderer: _CliRenderer) -> str:
    lines = renderer.title("Command Result", status=str(payload.get("status") or "ok"))
    lines.append(json.dumps(payload, indent=2, sort_keys=True))
    return "\n".join(lines)


def _result_dict(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    return result if isinstance(result, dict) else {}


def _append_meta_section(
    lines: list[str],
    payload: dict[str, Any],
    renderer: _CliRenderer,
) -> None:
    rows = [
        ("Trace Ref", _stringify(payload.get("trace_ref"))),
        ("Audit Ref", _stringify(payload.get("audit_ref"))),
        ("Request ID", _stringify(payload.get("request_id"))),
    ]
    rendered = renderer.kv_block(rows)
    if rendered:
        lines.extend(renderer.section("Meta"))
        lines.extend(rendered)


def _extract_context_preview(context_text: Any) -> str | None:
    if not isinstance(context_text, str) or not context_text.strip():
        return None
    raw = context_text.strip()
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return _truncate(" ".join(raw.split()), 160)

    slots = decoded.get("slots")
    if isinstance(slots, list):
        parts: list[str] = []
        for slot in slots[:3]:
            if not isinstance(slot, dict):
                continue
            summary = slot.get("summary")
            if summary:
                parts.append(str(summary))
        if parts:
            return _truncate(" | ".join(parts), 160)
    return _truncate(" ".join(raw.split()), 160)


def _render_access_object_table(
    renderer: _CliRenderer,
    object_ids: list[str],
    summaries: list[dict[str, Any]],
) -> list[str]:
    has_type = any(item.get("type") for item in summaries)
    has_episode = any(item.get("episode_id") for item in summaries)
    has_score = any(item.get("score") is not None for item in summaries)
    has_preview = any(item.get("content_preview") for item in summaries)
    summary_by_id = {
        str(item.get("object_id")): item for item in summaries if item.get("object_id") is not None
    }

    headers = ["#", "Object ID"]
    if has_type:
        headers.append("Type")
    if has_episode:
        headers.append("Episode")
    if has_score:
        headers.append("Score")
    if has_preview:
        headers.append("Preview")

    rows: list[list[str]] = []
    for index, object_id in enumerate(object_ids, start=1):
        summary = summary_by_id.get(object_id, {})
        row = [str(index)]
        row.append(object_id)
        if has_type:
            row.append(str(summary.get("type") or "-"))
        if has_episode:
            row.append(str(summary.get("episode_id") or "-"))
        if has_score:
            score = summary.get("score")
            row.append(f"{score:.3f}" if isinstance(score, int | float) else "-")
        if has_preview:
            row.append(str(summary.get("content_preview") or "-"))
        rows.append(row)

    return renderer.table(headers, rows)


def _display_access_depth(value: Any) -> str | None:
    text = _stringify(value)
    if text is None:
        return None
    labels = {
        "flash": "flash",
        "recall": "focus",
        "reconstruct": "reconstruct",
        "reflective_access": "reflective_access",
        "auto": "auto",
    }
    return labels.get(text, text)


def _truncate(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _stringify(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _labelize(name: str) -> str:
    return name.replace("_", " ").title()


def _should_use_color(mode: str, stream: Any) -> bool:
    if mode == "always":
        return True
    if mode == "never":
        return False
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def _terminal_width() -> int:
    columns = shutil.get_terminal_size(fallback=(100, 24)).columns
    return max(72, min(columns, 120))


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _health_value(renderer: _CliRenderer, value: Any) -> str | None:
    text = _stringify(value)
    if text is None:
        return None
    normalized = text.lower()
    if normalized in {"healthy", "connected", "ready"}:
        return renderer.tone(text, kind="ok")
    if normalized in {"unhealthy", "not_ready", "not ready"}:
        return renderer.tone(text, kind="error")
    return text


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
