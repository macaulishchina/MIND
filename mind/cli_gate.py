"""Unified CLI formal gate evaluation helpers."""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from mind.cli import _command_group_lookup, build_mind_parser
from mind.cli_gate_audits import (
    _AuditOutcome,
    _config_case_matches,  # noqa: F401
    _evaluate_config_audit,
    _evaluate_output_contract_audit,
    _invoke_mind,
    _output_value,  # noqa: F401
    _resolve_postgres_admin_dsn,
)
from mind.fixtures import build_mind_cli_scenario_set_v1

_SCHEMA_VERSION = "cli_gate_report_v1"
_HELP_EXPECTATIONS: dict[str, str] = {
    "primitive": "write-raw",
    "access": "run",
    "offline": "worker",
    "governance": "plan-conceal",
    "gate": "phase-b",
    "report": "acceptance",
    "demo": "ingest-read",
    "config": "show",
}


@dataclass(frozen=True)
class CliGateResult:
    scenario_count: int
    scenario_family_count: int
    help_coverage_count: int
    help_total: int
    family_reachability_count: int
    family_total: int
    representative_flow_pass_count: int
    representative_flow_total: int
    config_audit_pass_count: int
    config_audit_total: int
    output_contract_pass_count: int
    output_contract_total: int
    invalid_exit_coverage_count: int
    invalid_exit_total: int
    wrapped_regression_pass_count: int
    wrapped_regression_total: int
    postgres_demo_configured: bool
    help_failures: tuple[str, ...]
    family_failures: tuple[str, ...]
    representative_flow_failures: tuple[str, ...]
    config_audit_failures: tuple[str, ...]
    output_contract_failures: tuple[str, ...]
    invalid_exit_failures: tuple[str, ...]
    wrapped_regression_failures: tuple[str, ...]

    @property
    def j1_pass(self) -> bool:
        return self.help_total > 0 and self.help_coverage_count == self.help_total

    @property
    def j2_pass(self) -> bool:
        return (
            self.family_total == 8
            and self.family_reachability_count == self.family_total
            and self.scenario_family_count == 9
            and self.scenario_count >= 25
        )

    @property
    def j3_pass(self) -> bool:
        return (
            self.postgres_demo_configured
            and self.representative_flow_total > 0
            and self.representative_flow_pass_count == self.representative_flow_total
        )

    @property
    def j4_pass(self) -> bool:
        return (
            self.config_audit_total > 0 and self.config_audit_pass_count == self.config_audit_total
        )

    @property
    def j5_pass(self) -> bool:
        return (
            self.output_contract_total > 0
            and self.output_contract_pass_count == self.output_contract_total
            and self.invalid_exit_total > 0
            and self.invalid_exit_coverage_count == self.invalid_exit_total
        )

    @property
    def j6_pass(self) -> bool:
        return (
            self.wrapped_regression_total > 0
            and self.wrapped_regression_pass_count == self.wrapped_regression_total
        )

    @property
    def cli_gate_pass(self) -> bool:
        return (
            self.j1_pass
            and self.j2_pass
            and self.j3_pass
            and self.j4_pass
            and self.j5_pass
            and self.j6_pass
        )


def evaluate_cli_gate(postgres_admin_dsn: str | None = None) -> CliGateResult:
    """Run the formal unified CLI gate."""

    scenarios = build_mind_cli_scenario_set_v1()
    postgres_dsn = _resolve_postgres_admin_dsn(postgres_admin_dsn)
    help_audit = _evaluate_help_audit()
    family_audit = _evaluate_family_reachability_audit()
    representative_flows = _evaluate_representative_flow_audit(postgres_dsn)
    config_audit = _evaluate_config_audit()
    output_audit = _evaluate_output_contract_audit()
    invalid_exit_audit = _evaluate_invalid_exit_audit()
    wrapped_regression = _evaluate_wrapped_regression_audit()

    return CliGateResult(
        scenario_count=len(scenarios),
        scenario_family_count=len({scenario.command_family for scenario in scenarios}),
        help_coverage_count=help_audit.pass_count,
        help_total=help_audit.total,
        family_reachability_count=family_audit.pass_count,
        family_total=family_audit.total,
        representative_flow_pass_count=representative_flows.pass_count,
        representative_flow_total=representative_flows.total,
        config_audit_pass_count=config_audit.pass_count,
        config_audit_total=config_audit.total,
        output_contract_pass_count=output_audit.pass_count,
        output_contract_total=output_audit.total,
        invalid_exit_coverage_count=invalid_exit_audit.pass_count,
        invalid_exit_total=invalid_exit_audit.total,
        wrapped_regression_pass_count=wrapped_regression.pass_count,
        wrapped_regression_total=wrapped_regression.total,
        postgres_demo_configured=postgres_dsn is not None,
        help_failures=help_audit.failures,
        family_failures=family_audit.failures,
        representative_flow_failures=representative_flows.failures,
        config_audit_failures=config_audit.failures,
        output_contract_failures=output_audit.failures,
        invalid_exit_failures=invalid_exit_audit.failures,
        wrapped_regression_failures=wrapped_regression.failures,
    )


def assert_cli_gate(result: CliGateResult) -> None:
    if not result.j1_pass:
        help_failure_summary = list(result.help_failures)
        raise RuntimeError(
            "J-1 failed: CLI help coverage incomplete "
            f"({result.help_coverage_count}/{result.help_total}, "
            f"failures={help_failure_summary})"
        )
    if not result.j2_pass:
        raise RuntimeError(
            "J-2 failed: command-family coverage drift "
            f"(reachable={result.family_reachability_count}/{result.family_total}, "
            f"scenario_families={result.scenario_family_count}, "
            f"scenario_count={result.scenario_count}, failures={list(result.family_failures)})"
        )
    if not result.j3_pass:
        raise RuntimeError(
            "J-3 failed: representative CLI flows incomplete "
            f"(configured_postgres={result.postgres_demo_configured}, "
            f"flows={result.representative_flow_pass_count}/{result.representative_flow_total}, "
            f"failures={list(result.representative_flow_failures)})"
        )
    if not result.j4_pass:
        raise RuntimeError(
            "J-4 failed: config/backend audit drift "
            f"({result.config_audit_pass_count}/{result.config_audit_total}, "
            f"failures={list(result.config_audit_failures)})"
        )
    if not result.j5_pass:
        raise RuntimeError(
            "J-5 failed: output/exit contract drift "
            f"(output={result.output_contract_pass_count}/{result.output_contract_total}, "
            f"invalid_exit={result.invalid_exit_coverage_count}/{result.invalid_exit_total}, "
            f"output_failures={list(result.output_contract_failures)}, "
            f"invalid_failures={list(result.invalid_exit_failures)})"
        )
    if not result.j6_pass:
        raise RuntimeError(
            "J-6 failed: wrapped regression commands regressed "
            f"({result.wrapped_regression_pass_count}/{result.wrapped_regression_total}, "
            f"failures={list(result.wrapped_regression_failures)})"
        )


def write_cli_gate_report_json(path: str | Path, result: CliGateResult) -> Path:
    """Persist the full unified CLI gate result as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        **asdict(result),
        "j1_pass": result.j1_pass,
        "j2_pass": result.j2_pass,
        "j3_pass": result.j3_pass,
        "j4_pass": result.j4_pass,
        "j5_pass": result.j5_pass,
        "j6_pass": result.j6_pass,
        "cli_gate_pass": result.cli_gate_pass,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def _evaluate_help_audit() -> _AuditOutcome:
    failures: list[str] = []
    checks: list[tuple[tuple[str, ...], str]] = [(("mind", "-h"), "Unified CLI")]
    checks.extend(
        ((("mind", family), _HELP_EXPECTATIONS[family])) for family in _command_group_lookup()
    )

    pass_count = 0
    for argv, expected_fragment in checks:
        run = _invoke_mind(argv)
        if run.exit_code == 0 and expected_fragment in run.stdout:
            pass_count += 1
            continue
        failures.append(" ".join(argv))
    return _AuditOutcome(pass_count=pass_count, total=len(checks), failures=tuple(failures))


def _evaluate_family_reachability_audit() -> _AuditOutcome:
    failures: list[str] = []
    parser = build_mind_parser()
    parser_actions = [
        action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"
    ]
    parser_choices = parser_actions[0].choices if parser_actions else {}
    parser_families = set(parser_choices) if parser_choices is not None else set()
    scenario_families = {
        scenario.command_family
        for scenario in build_mind_cli_scenario_set_v1()
        if scenario.command_family != "help"
    }
    pass_count = 0
    for family in _command_group_lookup():
        run = _invoke_mind(("mind", family))
        if family in parser_families and family in scenario_families and run.exit_code == 0:
            pass_count += 1
            continue
        failures.append(family)
    return _AuditOutcome(
        pass_count=pass_count,
        total=len(_command_group_lookup()),
        failures=tuple(failures),
    )


def _evaluate_representative_flow_audit(postgres_admin_dsn: str | None) -> _AuditOutcome:
    failures: list[str] = []
    pass_count = 0
    total = 5
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "cli_flow.sqlite3"
        ingest = _invoke_mind(("mind", "demo", "ingest-read"))
        if ingest.exit_code == 0 and "read_object_count=1" in ingest.stdout:
            pass_count += 1
        else:
            failures.append("demo_ingest_read")

        write = _invoke_mind(
            (
                "mind",
                "primitive",
                "write-raw",
                "--sqlite-path",
                str(db_path),
                "--record-kind",
                "user_message",
                "--episode-id",
                "phase-j-retrieve",
                "--timestamp-order",
                "1",
                "--content",
                "phase j retrieve anchor",
            )
        )
        retrieve = _invoke_mind(
            (
                "mind",
                "primitive",
                "retrieve",
                "--sqlite-path",
                str(db_path),
                "--query",
                "retrieve anchor",
                "--object-type",
                "RawRecord",
            )
        )
        if (
            write.exit_code == 0
            and retrieve.exit_code == 0
            and "candidate_count=1" in retrieve.stdout
        ):
            pass_count += 1
        else:
            failures.append("primitive_retrieve")

        access_run = _invoke_mind(("mind", "demo", "access-run"))
        if access_run.exit_code == 0 and "trace_event_count=" in access_run.stdout:
            pass_count += 1
        else:
            failures.append("demo_access_run")

        if postgres_admin_dsn is not None:
            offline_job = _invoke_mind(
                (
                    "mind",
                    "demo",
                    "offline-job",
                    "--backend",
                    "postgresql",
                    "--dsn",
                    postgres_admin_dsn,
                )
            )
            if offline_job.exit_code == 0 and "pending_job_count=1" in offline_job.stdout:
                pass_count += 1
            else:
                failures.append("demo_offline_job")
        else:
            failures.append("demo_offline_job")

        gate_report = _invoke_mind(("mind", "report", "acceptance", "--phase", "h"))
        if gate_report.exit_code == 0 and "exists=true" in gate_report.stdout:
            pass_count += 1
        else:
            failures.append("report_acceptance_h")

    return _AuditOutcome(pass_count=pass_count, total=total, failures=tuple(failures))



def _evaluate_invalid_exit_audit() -> _AuditOutcome:
    checks = (
        ("primitive_write_raw_missing_args", ("mind", "primitive", "write-raw")),
        (
            "access_run_missing_query",
            ("mind", "access", "run", "--mode", "flash", "--task-id", "x"),
        ),
        ("governance_preview_missing_operation", ("mind", "governance", "preview")),
        ("demo_offline_job_missing_dsn", ("mind", "demo", "offline-job")),
        ("report_acceptance_missing_phase", ("mind", "report", "acceptance")),
    )
    failures: list[str] = []
    pass_count = 0
    for check_id, argv in checks:
        run = _invoke_mind(argv)
        if run.exit_code != 0:
            pass_count += 1
            continue
        failures.append(check_id)
    return _AuditOutcome(pass_count=pass_count, total=len(checks), failures=tuple(failures))


def _evaluate_wrapped_regression_audit() -> _AuditOutcome:
    failures: list[str] = []
    pass_count = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        checks = (
            ("gate_kernel", ("mind", "gate", "phase-b")),
            ("gate_primitive", ("mind", "gate", "phase-c")),
            (
                "gate_governance",
                ("mind", "gate", "phase-h", "--output", str(Path(tmpdir) / "governance.json")),
            ),
            (
                "gate_access",
                ("mind", "gate", "phase-i", "--output", str(Path(tmpdir) / "access.json")),
            ),
            ("report_acceptance_h", ("mind", "report", "acceptance", "--phase", "h")),
        )
        for check_id, argv in checks:
            run = _invoke_mind(argv)
            if run.exit_code == 0:
                pass_count += 1
                continue
            failures.append(check_id)
    return _AuditOutcome(pass_count=pass_count, total=len(checks), failures=tuple(failures))
