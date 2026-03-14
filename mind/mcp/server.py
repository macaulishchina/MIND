"""MCP tool catalog and server wrapper."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from mind.app.context import (
    ExecutionPolicy,
    NamespaceContext,
    PrincipalContext,
    ProviderSelection,
    SessionContext,
)
from mind.app.contracts import AppRequest, AppResponse
from mind.app.registry import AppServiceRegistry, build_app_registry
from mind.cli_config import ResolvedCliConfig
from mind.mcp.session import map_mcp_session

try:
    FastMCP = importlib.import_module("mcp.server.fastmcp").FastMCP
except ImportError:  # pragma: no cover - optional runtime dependency
    FastMCP = None

ToolHandler = Callable[[AppServiceRegistry, AppRequest], AppResponse]

_APP_ENVELOPE_KEYS = frozenset(
    {
        "idempotency_key",
        "input",
        "namespace",
        "policy",
        "provider_selection",
        "request_id",
        "session",
    }
)


@dataclass(frozen=True)
class MCPToolDefinition:
    """A single MCP tool definition."""

    name: str
    description: str
    input_schema: dict[str, Any]


class MindMCPServer:
    """Minimal MCP server wrapper backed by the shared app service registry."""

    def __init__(self, config: ResolvedCliConfig | None = None) -> None:
        self._config = config
        self._registry_cm: AbstractContextManager[AppServiceRegistry] | None = None
        self._registry: AppServiceRegistry | None = None
        self._tools = _tool_catalog()
        self._handlers = _tool_handlers()
        self.sdk_server = self._build_sdk_server()

    def __enter__(self) -> MindMCPServer:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        self.close()

    @property
    def sdk_available(self) -> bool:
        return self.sdk_server is not None

    def open(self) -> None:
        """Open and retain a shared app registry for multi-call sessions."""

        if self._registry is not None:
            return
        self._registry_cm = build_app_registry(self._config)
        self._registry = self._registry_cm.__enter__()

    def close(self) -> None:
        """Close the retained app registry if one is open."""

        if self._registry_cm is None:
            return
        self._registry_cm.__exit__(None, None, None)
        self._registry_cm = None
        self._registry = None

    def list_tools(self) -> tuple[MCPToolDefinition, ...]:
        """Return the full MCP tool catalog."""

        return self._tools

    def invoke_tool(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        client_info: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Invoke one tool through the application service layer."""

        if name not in self._handlers:
            raise KeyError(f"unknown MCP tool '{name}'")

        handler = self._handlers[name]
        if self._registry is not None:
            return self._invoke_with_registry(
                self._registry,
                handler,
                arguments=arguments,
                client_info=client_info,
            )

        with build_app_registry(self._config) as registry:
            return self._invoke_with_registry(
                registry,
                handler,
                arguments=arguments,
                client_info=client_info,
            )

    def _invoke_with_registry(
        self,
        registry: AppServiceRegistry,
        handler: ToolHandler,
        *,
        arguments: Mapping[str, Any] | None,
        client_info: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        raw_arguments = dict(arguments or {})
        request_id = str(raw_arguments.get("request_id") or f"mcp-{uuid4().hex[:16]}")
        principal, session = map_mcp_session(client_info, request_id=request_id)
        request = _build_app_request(raw_arguments, principal=principal, session=session)
        response = handler(registry, request)
        return response.model_dump(mode="json")

    def _build_sdk_server(self) -> Any | None:
        if FastMCP is None:
            return None

        server = FastMCP("MIND")
        for tool in self._tools:
            handler = self._handlers[tool.name]
            server.tool(name=tool.name, description=tool.description)(
                _sdk_tool_wrapper(self, handler)
            )
        return server


def create_mcp_server(config: ResolvedCliConfig | None = None) -> MindMCPServer:
    """Create the MCP server wrapper."""

    return MindMCPServer(config)


def run_mcp() -> None:
    """Run the MCP server via the official SDK when available."""

    server = create_mcp_server()
    if server.sdk_server is None:
        raise RuntimeError(
            "The official 'mcp' package is not installed. Install the project with mind[mcp]."
        )
    run_method = getattr(server.sdk_server, "run", None)
    if not callable(run_method):
        raise RuntimeError("Installed MCP SDK does not expose a runnable FastMCP server")
    run_method()


def _build_app_request(
    arguments: Mapping[str, Any],
    *,
    principal: PrincipalContext,
    session: SessionContext,
) -> AppRequest:
    request_id = str(arguments.get("request_id") or session.request_id or f"mcp-{uuid4().hex[:16]}")
    session_payload = session.model_dump(mode="json")
    if isinstance(arguments.get("session"), dict):
        session_payload.update(dict(arguments["session"]))
    session_payload["request_id"] = request_id

    namespace = (
        NamespaceContext.model_validate(arguments["namespace"])
        if isinstance(arguments.get("namespace"), dict)
        else None
    )
    policy = (
        ExecutionPolicy.model_validate(arguments["policy"])
        if isinstance(arguments.get("policy"), dict)
        else None
    )
    provider_selection = (
        ProviderSelection.model_validate(arguments["provider_selection"])
        if isinstance(arguments.get("provider_selection"), dict)
        else None
    )
    input_payload = (
        dict(arguments["input"])
        if isinstance(arguments.get("input"), dict)
        else {key: value for key, value in arguments.items() if key not in _APP_ENVELOPE_KEYS}
    )
    return AppRequest(
        request_id=request_id,
        idempotency_key=arguments.get("idempotency_key"),
        principal=principal,
        namespace=namespace,
        session=SessionContext.model_validate(session_payload),
        policy=policy,
        provider_selection=provider_selection,
        input=input_payload,
    )


def _tool_catalog() -> tuple[MCPToolDefinition, ...]:
    return (
        MCPToolDefinition(
            name="remember",
            description="Store one memory object.",
            input_schema=_object_schema("content", "episode_id"),
        ),
        MCPToolDefinition(
            name="recall",
            description="Recall memories by query.",
            input_schema=_object_schema("query"),
        ),
        MCPToolDefinition(
            name="ask_memory",
            description="Ask a question against stored memory.",
            input_schema=_object_schema("query"),
        ),
        MCPToolDefinition(
            name="get_memory",
            description="Fetch one memory by id.",
            input_schema=_object_schema("object_id"),
        ),
        MCPToolDefinition(
            name="list_memories",
            description="List recent memories.",
            input_schema=_object_schema(),
        ),
        MCPToolDefinition(
            name="search_memories",
            description="Search memories using the retrieval backend.",
            input_schema=_object_schema("query"),
        ),
        MCPToolDefinition(
            name="plan_conceal",
            description="Plan a governance concealment operation.",
            input_schema=_object_schema("reason"),
        ),
        MCPToolDefinition(
            name="preview_conceal",
            description="Preview a planned governance concealment.",
            input_schema=_object_schema("operation_id"),
        ),
        MCPToolDefinition(
            name="execute_conceal",
            description="Execute a planned governance concealment.",
            input_schema=_object_schema("operation_id"),
        ),
        MCPToolDefinition(
            name="submit_offline_job",
            description="Submit a background offline maintenance job.",
            input_schema=_object_schema("job_kind", "payload"),
        ),
        MCPToolDefinition(
            name="get_job_status",
            description="Get one offline maintenance job by id.",
            input_schema=_object_schema("job_id"),
        ),
        MCPToolDefinition(
            name="record_feedback",
            description="Record post-query feedback on memory objects.",
            input_schema=_object_schema(
                "task_id",
                "episode_id",
                "query",
                "used_object_ids",
                "helpful_object_ids",
                "quality_signal",
            ),
        ),
    )


def _tool_handlers() -> dict[str, ToolHandler]:
    return {
        "remember": lambda registry, req: registry.memory_ingest_service.remember(req),
        "recall": lambda registry, req: registry.memory_query_service.recall(req),
        "ask_memory": lambda registry, req: registry.memory_access_service.ask(req),
        "get_memory": lambda registry, req: registry.memory_query_service.get_memory(req),
        "list_memories": lambda registry, req: registry.memory_query_service.list_memories(req),
        "search_memories": lambda registry, req: registry.memory_query_service.search(req),
        "plan_conceal": lambda registry, req: registry.governance_app_service.plan_conceal(req),
        "preview_conceal": lambda registry, req: registry.governance_app_service.preview_conceal(
            req
        ),
        "execute_conceal": lambda registry, req: registry.governance_app_service.execute_conceal(
            req
        ),
        "submit_offline_job": lambda registry, req: registry.offline_job_app_service.submit_job(
            req
        ),
        "get_job_status": lambda registry, req: registry.offline_job_app_service.get_job(req),
        "record_feedback": lambda registry, req: registry.feedback_service.record_feedback(req),
    }


def _object_schema(*required: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {},
        "required": list(required),
        "additionalProperties": True,
    }


def _sdk_tool_wrapper(server: MindMCPServer, handler: ToolHandler) -> Callable[..., Any]:
    async def wrapped_tool(**arguments: Any) -> dict[str, Any]:
        if server._registry is not None:
            registry = server._registry
            assert registry is not None
            return server._invoke_with_registry(
                registry,
                handler,
                arguments=arguments,
                client_info=None,
            )
        with build_app_registry(server._config) as registry:
            return server._invoke_with_registry(
                registry,
                handler,
                arguments=arguments,
                client_info=None,
            )

    return wrapped_tool
