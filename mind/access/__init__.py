"""Runtime access mode contracts."""

from .benchmark import (
    AccessBenchmarkResult,
    AccessBenchmarkRun,
    AccessFrontierComparison,
    AccessModeFamilyAggregate,
    evaluate_access_benchmark,
    merge_access_benchmark_results,
)
from .contracts import (
    AccessContextKind,
    AccessMode,
    AccessModeRequest,
    AccessModeTraceEvent,
    AccessReasonCode,
    AccessRunRequest,
    AccessRunResponse,
    AccessRunTrace,
    AccessSwitchKind,
    AccessTaskFamily,
    AccessTraceKind,
)
from .gate import (
    AccessAutoAuditResult,
    AccessGateResult,
    assert_access_gate,
    build_access_gate_result,
    evaluate_access_auto_audit,
    evaluate_access_fixed_lock_audit,
    evaluate_access_gate,
    write_access_gate_report_json,
)
from .service import AccessService, AccessServiceError

__all__ = [
    "AccessAutoAuditResult",
    "AccessBenchmarkResult",
    "AccessBenchmarkRun",
    "AccessContextKind",
    "AccessFrontierComparison",
    "AccessMode",
    "AccessModeRequest",
    "AccessModeTraceEvent",
    "AccessModeFamilyAggregate",
    "AccessReasonCode",
    "AccessRunRequest",
    "AccessRunResponse",
    "AccessRunTrace",
    "AccessService",
    "AccessServiceError",
    "AccessSwitchKind",
    "AccessTaskFamily",
    "AccessTraceKind",
    "AccessGateResult",
    "assert_access_gate",
    "build_access_gate_result",
    "evaluate_access_benchmark",
    "evaluate_access_auto_audit",
    "evaluate_access_fixed_lock_audit",
    "evaluate_access_gate",
    "merge_access_benchmark_results",
    "write_access_gate_report_json",
]
