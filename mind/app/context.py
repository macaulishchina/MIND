"""Product execution contexts for the Application Service Layer."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from os import environ

from pydantic import BaseModel, ConfigDict, Field

from mind.access import AccessMode
from mind.kernel.provenance import (
    DirectProvenanceInput,
    ProducerKind,
)
from mind.kernel.provenance import (
    SourceChannel as ProvenanceSourceChannel,
)
from mind.primitives.contracts import Capability, PrimitiveExecutionContext

_TRUE_ENV_VALUES = frozenset({"1", "true", "yes", "on"})

# ---------------------------------------------------------------------------
# Supporting enums
# ---------------------------------------------------------------------------

class PrincipalKind(StrEnum):
    """Kinds of principal identities."""

    USER = "user"
    SERVICE = "service"
    SYSTEM = "system"
    API_KEY = "api_key"


class SourceChannel(StrEnum):
    """Communication channels."""

    CLI = "cli"
    REST = "rest"
    MCP = "mcp"
    INTERNAL = "internal"


class RetentionClass(StrEnum):
    """Data retention classifications."""

    STANDARD = "standard"
    TRANSIENT = "transient"
    LONG_TERM = "long_term"


# ---------------------------------------------------------------------------
# Frozen context models
# ---------------------------------------------------------------------------

class PrincipalContext(BaseModel):
    """Identity context for the acting principal."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str = Field(min_length=1)
    principal_kind: PrincipalKind = PrincipalKind.USER
    tenant_id: str = Field(default="default", min_length=1)
    user_id: str | None = None
    roles: list[str] = Field(default_factory=list)
    capabilities: list[Capability] = Field(
        default_factory=lambda: [Capability.MEMORY_READ],
    )


class NamespaceContext(BaseModel):
    """Logical namespace scoping for multi-tenant isolation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    namespace_id: str = Field(min_length=1)
    tenant_id: str = Field(default="default", min_length=1)
    project_id: str | None = None
    workspace_id: str | None = None
    memory_visibility_policy: str = "default"


class SessionContext(BaseModel):
    """Ephemeral session state for request correlation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str = Field(min_length=1)
    conversation_id: str | None = None
    channel: SourceChannel = SourceChannel.INTERNAL
    client_id: str | None = None
    device_id: str | None = None
    request_id: str | None = None


class ExecutionPolicy(BaseModel):
    """Execution-time policy and budget configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    default_access_mode: AccessMode = AccessMode.AUTO
    budget_limit: float | None = None
    retention_class: RetentionClass = RetentionClass.STANDARD
    dev_mode: bool = False
    conceal_visibility: bool = False
    fallback_policy: str = "reject"


class ProviderSelection(BaseModel):
    """LLM/embedding provider routing info (reserved for WP-7)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = "stub"
    model: str = "deterministic"
    endpoint: str | None = None
    timeout_ms: int = Field(default=30_000, ge=100)
    retry_policy: str = "default"


# ---------------------------------------------------------------------------
# Context projection
# ---------------------------------------------------------------------------

def resolve_execution_context(
    principal: PrincipalContext | None = None,
    session: SessionContext | None = None,
    policy: ExecutionPolicy | None = None,
) -> PrimitiveExecutionContext:
    """Project product contexts into the existing domain execution context."""

    actor = "system"
    if principal is not None:
        actor = principal.principal_id

    budget_scope_id = "global"
    if session is not None and session.session_id:
        budget_scope_id = session.session_id

    budget_limit: float | None = None
    if policy is not None and policy.budget_limit is not None:
        budget_limit = policy.budget_limit

    capabilities: list[Capability] = [Capability.MEMORY_READ]
    if principal is not None:
        capabilities = list(principal.capabilities)

    dev_mode = policy.dev_mode if policy is not None else _env_dev_mode()

    return PrimitiveExecutionContext(
        actor=actor,
        budget_scope_id=budget_scope_id,
        budget_limit=budget_limit,
        capabilities=capabilities,
        dev_mode=dev_mode,
        telemetry_run_id=(
            session.request_id
            if session is not None and session.request_id
            else session.session_id if session is not None else None
        ),
    )


def project_provenance_from_context(
    principal: PrincipalContext | None = None,
    session: SessionContext | None = None,
    namespace: NamespaceContext | None = None,
) -> DirectProvenanceInput:
    """Project product contexts into the DirectProvenanceInput contract."""

    tenant_id = "default"
    if principal is not None:
        tenant_id = principal.tenant_id
    elif namespace is not None:
        tenant_id = namespace.tenant_id

    return DirectProvenanceInput(
        producer_kind=_producer_kind_for(principal.principal_kind if principal else None),
        producer_id=principal.principal_id if principal is not None else "system",
        captured_at=datetime.now(UTC),
        source_channel=_provenance_channel_for(session.channel if session else None),
        tenant_id=tenant_id,
        user_id=principal.user_id if principal is not None else None,
        device_id=session.device_id if session is not None else None,
        session_id=session.session_id if session is not None else None,
        request_id=session.request_id if session is not None else None,
        conversation_id=session.conversation_id if session is not None else None,
    )


def _producer_kind_for(principal_kind: PrincipalKind | None) -> ProducerKind:
    if principal_kind is PrincipalKind.USER:
        return ProducerKind.USER
    if principal_kind is PrincipalKind.SERVICE:
        return ProducerKind.TOOL
    if principal_kind is PrincipalKind.API_KEY:
        return ProducerKind.OPERATOR
    return ProducerKind.SYSTEM


def _env_dev_mode() -> bool:
    return environ.get("MIND_DEV_MODE", "").strip().lower() in _TRUE_ENV_VALUES


def _provenance_channel_for(
    channel: SourceChannel | None,
) -> ProvenanceSourceChannel:
    if channel is SourceChannel.CLI:
        return ProvenanceSourceChannel.CHAT
    if channel is SourceChannel.REST:
        return ProvenanceSourceChannel.API
    if channel is SourceChannel.MCP:
        return ProvenanceSourceChannel.TOOL_RUNTIME
    return ProvenanceSourceChannel.SYSTEM_INTERNAL
