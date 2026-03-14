"""Governance control-plane interfaces."""

from .gate import (
    GovernanceGateResult,
    evaluate_governance_gate,
)
from .gate_helpers import assert_governance_gate, write_governance_gate_report_json
from .service import GovernanceService, GovernanceServiceError

__all__ = [
    "GovernanceService",
    "GovernanceServiceError",
    "GovernanceGateResult",
    "assert_governance_gate",
    "evaluate_governance_gate",
    "write_governance_gate_report_json",
]
