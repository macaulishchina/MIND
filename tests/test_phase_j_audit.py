"""Phase J independent audit – supplementary tests.

These tests verify issues found during the Phase J audit and provide
additional coverage for the restructured codebase.

Audit ref: docs/reports/phase_j_independent_audit.md
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from mind.cli import _ACCEPTANCE_REPORTS, build_mind_parser, mind_main

# ---------------------------------------------------------------------------
# DEFECT-1 regression: _ACCEPTANCE_REPORTS must include phase "j"
# ---------------------------------------------------------------------------


class TestAcceptanceReportsCatalog:
    """Verify that the acceptance report catalog contains all required phases."""

    REQUIRED_PHASES = ("a", "b", "c", "d", "e", "f", "g", "h", "i", "j")

    def test_acceptance_reports_contains_all_phases(self) -> None:
        for phase in self.REQUIRED_PHASES:
            assert phase in _ACCEPTANCE_REPORTS, f"_ACCEPTANCE_REPORTS is missing phase '{phase}'"

    def test_acceptance_reports_paths_all_exist(self) -> None:
        for phase, path in _ACCEPTANCE_REPORTS.items():
            assert path.exists(), f"Acceptance report for phase '{phase}' does not exist at {path}"

    def test_acceptance_report_phase_j_via_cli(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        exit_code = mind_main(["report", "acceptance", "--phase", "j"])
        assert exit_code == 0
        output = capsys.readouterr().out
        assert "phase=j" in output
        assert "docs/reports/phase_j_acceptance_report.md" in output
        assert "exists=true" in output

    def test_report_acceptance_parser_includes_phase_j(self) -> None:
        parser = build_mind_parser()
        # Verify that --phase j does not raise an error
        args = parser.parse_args(["report", "acceptance", "--phase", "j"])
        assert args.phase == "j"


# ---------------------------------------------------------------------------
# Restructured module export verification
# ---------------------------------------------------------------------------


class TestRestructuredExports:
    """Verify that all renamed gate modules are importable via the new paths
    AND that old phase_X.py paths no longer exist on disk."""

    OLD_MODULE_PATHS = (
        "mind/kernel/phase_b.py",
        "mind/primitives/phase_c.py",
        "mind/workspace/phase_d.py",
        "mind/offline/phase_e.py",
        "mind/eval/phase_f.py",
        "mind/eval/phase_g.py",
        "mind/governance/phase_h.py",
        "mind/access/phase_i.py",
    )

    NEW_IMPORTS = {
        "mind.kernel.gate": (
            "KernelGateResult",
            "evaluate_kernel_gate",
            "assert_kernel_gate",
        ),
        "mind.primitives.gate": (
            "PrimitiveGateResult",
            "evaluate_primitive_gate",
            "assert_primitive_gate",
        ),
        "mind.workspace.smoke": (
            "WorkspaceSmokeResult",
            "evaluate_workspace_smoke",
            "assert_workspace_smoke",
        ),
        "mind.offline.assessment": (
            "OfflineGateResult",
            "evaluate_offline_gate",
            "assert_offline_gate",
        ),
        "mind.eval.benchmark_gate": (
            "BenchmarkGateResult",
            "evaluate_benchmark_gate",
            "assert_benchmark_gate",
        ),
        "mind.eval.strategy_gate": (
            "StrategyGateResult",
            "evaluate_strategy_gate",
            "assert_strategy_gate",
        ),
        "mind.governance.gate": (
            "GovernanceGateResult",
            "evaluate_governance_gate",
            "assert_governance_gate",
        ),
        "mind.access.gate": (
            "AccessGateResult",
            "evaluate_access_gate",
            "assert_access_gate",
        ),
    }

    @pytest.mark.parametrize("old_path", OLD_MODULE_PATHS)
    def test_old_phase_file_no_longer_exists(self, old_path: str) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        full_path = repo_root / old_path
        assert not full_path.exists(), f"Stale phase file still exists: {old_path}"

    @pytest.mark.parametrize("module_path,names", list(NEW_IMPORTS.items()))
    def test_new_gate_module_importable(self, module_path: str, names: tuple[str, ...]) -> None:
        mod = importlib.import_module(module_path)
        for name in names:
            assert hasattr(mod, name), f"{module_path} is missing expected export '{name}'"

    def test_package_init_reexports_kernel_gate(self) -> None:
        from mind.kernel.gate import KernelGateResult, evaluate_kernel_gate

        assert KernelGateResult is not None
        assert callable(evaluate_kernel_gate)

    def test_package_init_reexports_offline_assessment(self) -> None:
        from mind.offline import (
            OfflineGateResult,
            assert_offline_gate,
            evaluate_offline_gate,
        )

        assert OfflineGateResult is not None
        assert callable(evaluate_offline_gate)
        assert callable(assert_offline_gate)

    def test_package_init_reexports_governance_gate(self) -> None:
        from mind.governance import (
            GovernanceGateResult,
            assert_governance_gate,
            evaluate_governance_gate,
        )

        assert GovernanceGateResult is not None
        assert callable(evaluate_governance_gate)
        assert callable(assert_governance_gate)

    def test_package_init_reexports_access_gate(self) -> None:
        from mind.access import (
            AccessGateResult,
            assert_access_gate,
            evaluate_access_gate,
        )

        assert AccessGateResult is not None
        assert callable(evaluate_access_gate)
        assert callable(assert_access_gate)

    def test_package_init_reexports_eval_gates(self) -> None:
        from mind.eval import (
            BenchmarkGateResult,
            StrategyGateResult,
            assert_benchmark_gate,
            assert_strategy_gate,
            evaluate_benchmark_gate,
            evaluate_strategy_gate,
        )

        assert BenchmarkGateResult is not None
        assert callable(evaluate_benchmark_gate)
        assert callable(assert_benchmark_gate)
        assert StrategyGateResult is not None
        assert callable(evaluate_strategy_gate)
        assert callable(assert_strategy_gate)

    def test_package_init_reexports_workspace_smoke(self) -> None:
        from mind.workspace import (
            WorkspaceSmokeResult,
            assert_workspace_smoke,
            evaluate_workspace_smoke,
        )

        assert WorkspaceSmokeResult is not None
        assert callable(evaluate_workspace_smoke)
        assert callable(assert_workspace_smoke)


# ---------------------------------------------------------------------------
# build_canonical_seed_objects rename verification
# ---------------------------------------------------------------------------


def test_build_canonical_seed_objects_is_importable() -> None:
    """Verify that the renamed helper function is reachable."""
    from mind.offline.assessment import build_canonical_seed_objects

    assert callable(build_canonical_seed_objects)


def test_no_stale_build_phase_d_seed_objects_reference() -> None:
    """Grep for old function name in Python source files."""
    repo_root = Path(__file__).resolve().parent.parent
    mind_dir = repo_root / "mind"
    stale_hits: list[str] = []
    for py_file in mind_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        text = py_file.read_text(encoding="utf-8")
        if "build_phase_d_seed_objects" in text:
            stale_hits.append(str(py_file.relative_to(repo_root)))
    assert stale_hits == [], f"Stale reference to build_phase_d_seed_objects in: {stale_hits}"


# ---------------------------------------------------------------------------
# CLI gate module structure verification
# ---------------------------------------------------------------------------


class TestCliGateModuleStructure:
    """Verify the cli_gate module (was phase_j.py) has correct structure."""

    def test_cli_gate_module_exists(self) -> None:
        mod = importlib.import_module("mind.cli_gate")
        assert hasattr(mod, "CliGateResult")
        assert hasattr(mod, "evaluate_cli_gate")
        assert hasattr(mod, "assert_cli_gate")
        assert hasattr(mod, "write_cli_gate_report_json")

    def test_cli_gate_result_properties_cover_j1_through_j6(self) -> None:
        from mind.cli_gate import CliGateResult

        for jx in ("j1_pass", "j2_pass", "j3_pass", "j4_pass", "j5_pass", "j6_pass"):
            assert hasattr(CliGateResult, jx), f"CliGateResult missing property '{jx}'"

    def test_cli_gate_pass_property_exists(self) -> None:
        from mind.cli_gate import CliGateResult

        assert hasattr(CliGateResult, "cli_gate_pass")


# ---------------------------------------------------------------------------
# Entry-point consistency
# ---------------------------------------------------------------------------


class TestEntryPointConsistency:
    """Verify pyproject.toml entry points reference existing functions."""

    def test_all_gate_main_functions_importable(self) -> None:
        gate_mains = [
            ("mind.cli", "kernel_gate_main"),
            ("mind.cli", "primitive_gate_main"),
            ("mind.cli", "offline_gate_main"),
            ("mind.cli", "governance_gate_main"),
            ("mind.cli", "access_gate_main"),
            ("mind.cli", "cli_gate_main"),
            ("mind.cli", "benchmark_gate_main"),
            ("mind.cli", "strategy_gate_main"),
            ("mind.cli", "product_readiness_gate_main"),
            ("mind.cli", "mind_main"),
        ]
        for module_path, func_name in gate_mains:
            mod = importlib.import_module(module_path)
            assert hasattr(mod, func_name), (
                f"{module_path} is missing entry point function '{func_name}'"
            )
            assert callable(getattr(mod, func_name))
