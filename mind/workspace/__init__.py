"""Workspace builder interfaces."""

from .builder import WorkspaceBuilder, WorkspaceBuildError, WorkspaceBuildResult
from .context_protocol import (
    WORKSPACE_CONTEXT_PROTOCOL,
    SerializedContext,
    build_raw_topk_context,
    build_workspace_context,
)
from .policy import (
    FLASH_POLICY,
    RECALL_POLICY,
    RECONSTRUCT_POLICY,
    REFLECTIVE_POLICY,
    SlotAllocationPolicy,
    apply_diversity_policy,
    evidence_diversity_score,
)
from .smoke import (
    RetrievalBenchmarkRun,
    WorkspaceSmokeResult,
    assert_workspace_smoke,
    evaluate_workspace_smoke,
)

__all__ = [
    "FLASH_POLICY",
    "RECALL_POLICY",
    "RECONSTRUCT_POLICY",
    "REFLECTIVE_POLICY",
    "WORKSPACE_CONTEXT_PROTOCOL",
    "WorkspaceSmokeResult",
    "RetrievalBenchmarkRun",
    "SerializedContext",
    "SlotAllocationPolicy",
    "WorkspaceBuildError",
    "WorkspaceBuildResult",
    "WorkspaceBuilder",
    "apply_diversity_policy",
    "assert_workspace_smoke",
    "build_raw_topk_context",
    "build_workspace_context",
    "evaluate_workspace_smoke",
    "evidence_diversity_score",
]
