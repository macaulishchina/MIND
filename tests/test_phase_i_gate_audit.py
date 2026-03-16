from __future__ import annotations

import pytest

from mind.access import AccessMode
from tests._phase_i_gate_support import auto_audit, fixed_lock_runs


@pytest.mark.parametrize(
    "mode",
    (
        AccessMode.FLASH,
        AccessMode.RECALL,
        AccessMode.RECONSTRUCT,
        AccessMode.REFLECTIVE_ACCESS,
    ),
)
def test_phase_i_fixed_lock_audit_never_overrides_explicit_mode(mode: AccessMode) -> None:
    runs = fixed_lock_runs(mode)

    assert runs
    assert all(run.trace.requested_mode is mode for run in runs)
    assert all(run.trace.resolved_mode is mode for run in runs)
    assert all(run.resolved_mode is mode for run in runs)


def test_phase_i_auto_audit_surfaces_upgrade_downgrade_and_jump_behavior() -> None:
    result = auto_audit()

    assert result.audited_run_count > 0
    assert result.switch_run_count > 0
    assert result.total_switch_count >= result.switch_run_count
    assert result.upgrade_count > 0
    assert result.downgrade_count > 0
    assert result.jump_count > 0
    assert result.missing_reason_code_count == 0
    assert result.missing_summary_count == 0
    assert result.oscillation_case_count == 0
