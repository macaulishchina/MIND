"""Application Service Layer — unified product boundary for MIND.

All transports (REST, MCP, CLI) share this layer.
"""

from __future__ import annotations

from mind.app.context import (
    ExecutionPolicy,
    NamespaceContext,
    PrincipalContext,
    PrincipalKind,
    ProviderSelection,
    RetentionClass,
    SessionContext,
    SourceChannel,
    project_provenance_from_context,
    resolve_execution_context,
)
from mind.app.contracts import AppError, AppErrorCode, AppRequest, AppResponse, AppStatus
from mind.app.errors import (
    AppServiceError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
    map_domain_error,
    map_primitive_error,
)
from mind.app.registry import AppServiceRegistry, build_app_registry
from mind.app.services import (
    GovernanceAppService,
    MemoryAccessService,
    MemoryIngestService,
    MemoryQueryService,
    OfflineJobAppService,
    SystemStatusService,
    UserStateService,
)

__all__ = [
    "AppError",
    "AppErrorCode",
    "AppRequest",
    "AppResponse",
    "AppServiceRegistry",
    "AppServiceError",
    "AppStatus",
    "AuthorizationError",
    "ConflictError",
    "ExecutionPolicy",
    "GovernanceAppService",
    "MemoryAccessService",
    "MemoryIngestService",
    "MemoryQueryService",
    "NamespaceContext",
    "NotFoundError",
    "OfflineJobAppService",
    "PrincipalContext",
    "PrincipalKind",
    "ProviderSelection",
    "RetentionClass",
    "SessionContext",
    "SourceChannel",
    "SystemStatusService",
    "UserStateService",
    "ValidationError",
    "build_app_registry",
    "map_domain_error",
    "map_primitive_error",
    "project_provenance_from_context",
    "resolve_execution_context",
]
