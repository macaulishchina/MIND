"""Project CLI entry points."""

from __future__ import annotations

import tempfile
from pathlib import Path

from .kernel.phase_b import assert_phase_b_gate, evaluate_phase_b_gate
from .primitives.phase_c import assert_phase_c_gate, evaluate_phase_c_gate


def phase_b_gate_main() -> int:
    """Run the local Phase B gate baseline check."""

    with tempfile.TemporaryDirectory() as tmpdir:
        result = evaluate_phase_b_gate(Path(tmpdir) / "phase_b.sqlite3")

    try:
        assert_phase_b_gate(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    print("Phase B gate baseline report")
    print(f"golden_episodes={result.golden_episode_count}")
    print(f"core_object_types={result.core_object_type_count}")
    print(f"round_trip_objects={result.round_trip_match_count}/{result.round_trip_total}")
    print(f"replay_matches={result.replay_match_count}/{result.replay_total}")
    print(f"source_trace_coverage={result.integrity_report.source_trace_coverage:.2f}")
    print(f"metadata_coverage={result.integrity_report.metadata_coverage:.2f}")
    print(f"dangling_refs={len(result.integrity_report.dangling_refs)}")
    print(f"cycles={len(result.integrity_report.cycles)}")
    print(f"version_chain_issues={len(result.integrity_report.version_chain_issues)}")
    print(f"B-1={'PASS' if result.b1_pass else 'FAIL'}")
    print(f"B-2={'PASS' if result.b2_pass else 'FAIL'}")
    print(f"B-3={'PASS' if result.b3_pass else 'FAIL'}")
    print(f"B-4={'PASS' if result.b4_pass else 'FAIL'}")
    print(f"B-5={'PASS' if result.b5_pass else 'FAIL'}")
    print(f"phase_b_gate={'PASS' if result.phase_b_pass else 'FAIL'}")
    return 0


def phase_c_gate_main() -> int:
    """Run the local Phase C gate baseline check."""

    with tempfile.TemporaryDirectory() as tmpdir:
        result = evaluate_phase_c_gate(Path(tmpdir) / "phase_c.sqlite3")

    try:
        assert_phase_c_gate(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    print("Phase C gate baseline report")
    print(f"primitive_golden_calls={result.total_calls}")
    print(f"expectation_matches={result.expectation_match_count}/{result.total_calls}")
    print(f"schema_valid_calls={result.schema_valid_calls}/{result.total_calls}")
    print(f"structured_log_calls={result.structured_log_calls}/{result.total_calls}")
    print(f"smoke_coverage={result.smoke_success_count}/7")
    print(
        "budget_rejections="
        f"{result.budget_rejection_match_count}/{result.budget_total}"
    )
    print(f"rollback_atomic={result.rollback_atomic_count}/{result.rollback_total}")
    print(f"C-1={'PASS' if result.c1_pass else 'FAIL'}")
    print(f"C-2={'PASS' if result.c2_pass else 'FAIL'}")
    print(f"C-3={'PASS' if result.c3_pass else 'FAIL'}")
    print(f"C-4={'PASS' if result.c4_pass else 'FAIL'}")
    print(f"C-5={'PASS' if result.c5_pass else 'FAIL'}")
    print(f"phase_c_gate={'PASS' if result.phase_c_pass else 'FAIL'}")
    return 0
