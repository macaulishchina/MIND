"""Workspace builder interfaces."""

from .builder import WorkspaceBuilder, WorkspaceBuildError, WorkspaceBuildResult
from .context_protocol import (
    WORKSPACE_CONTEXT_PROTOCOL,
    SerializedContext,
    build_raw_topk_context,
    build_workspace_context,
)
from .smoke import (
    RetrievalBenchmarkRun,
    WorkspaceSmokeResult,
    assert_workspace_smoke,
    evaluate_workspace_smoke,
)

__all__ = [
    "WORKSPACE_CONTEXT_PROTOCOL",
    "WorkspaceSmokeResult",
    "RetrievalBenchmarkRun",
    "SerializedContext",
    "WorkspaceBuildError",
    "WorkspaceBuildResult",
    "WorkspaceBuilder",
    "assert_workspace_smoke",
    "build_raw_topk_context",
    "build_workspace_context",
    "evaluate_workspace_smoke",
]
