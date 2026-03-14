"""MCP session to product context mapping."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from mind.app.context import (
    Capability,
    PrincipalContext,
    PrincipalKind,
    SessionContext,
    SourceChannel,
)


def map_mcp_session(
    client_info: Mapping[str, Any] | None = None,
    *,
    request_id: str | None = None,
) -> tuple[PrincipalContext, SessionContext]:
    """Map MCP client/session metadata into product-layer contexts."""

    payload = dict(client_info or {})
    principal_payload = (
        dict(payload.get("principal", {})) if isinstance(payload.get("principal"), dict) else {}
    )
    principal_payload.setdefault(
        "principal_id",
        payload.get("principal_id") or payload.get("client_id") or "mcp-client",
    )
    principal_payload.setdefault(
        "principal_kind",
        payload.get("principal_kind", PrincipalKind.SERVICE),
    )
    principal_payload.setdefault("tenant_id", payload.get("tenant_id", "default"))
    principal_payload.setdefault("user_id", payload.get("user_id"))
    principal_payload.setdefault("roles", list(payload.get("roles", ["mcp"])))
    principal_payload.setdefault(
        "capabilities",
        payload.get("capabilities", [capability.value for capability in Capability]),
    )
    principal = PrincipalContext.model_validate(principal_payload)

    session_payload = (
        dict(payload.get("session", {})) if isinstance(payload.get("session"), dict) else {}
    )
    session_payload.setdefault(
        "session_id",
        payload.get("session_id")
        or payload.get("conversation_id")
        or f"mcp-session-{uuid4().hex[:8]}",
    )
    session_payload.setdefault("conversation_id", payload.get("conversation_id"))
    session_payload.setdefault("channel", SourceChannel.MCP)
    session_payload.setdefault("client_id", payload.get("client_id"))
    session_payload.setdefault("device_id", payload.get("device_id"))
    session_payload.setdefault(
        "request_id",
        request_id or payload.get("request_id") or f"mcp-{uuid4().hex[:16]}",
    )
    session = SessionContext.model_validate(session_payload)
    return principal, session
