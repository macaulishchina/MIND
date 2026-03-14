"""CLI gate audit evaluation helpers and shared utilities."""

from __future__ import annotations

import os
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

from mind.cli import mind_main
from mind.cli_config import CliBackend, CliProfile, resolve_cli_config


@dataclass(frozen=True)
class _AuditOutcome:
    pass_count: int
    total: int
    failures: tuple[str, ...] = ()


@dataclass(frozen=True)
class _CommandRun:
    argv: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str


def _resolve_postgres_admin_dsn(postgres_admin_dsn: str | None) -> str | None:
    return (
        postgres_admin_dsn
        or os.environ.get("MIND_TEST_POSTGRES_DSN")
        or os.environ.get("MIND_POSTGRES_DSN")
    )


def _invoke_mind(argv: tuple[str, ...]) -> _CommandRun:
    normalized_argv = argv[1:] if argv and argv[0] == "mind" else argv
    stdout = StringIO()
    stderr = StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = mind_main(list(normalized_argv))
    except SystemExit as exc:
        code = exc.code
        exit_code = code if isinstance(code, int) else 1
    return _CommandRun(
        argv=argv,
        exit_code=exit_code,
        stdout=stdout.getvalue(),
        stderr=stderr.getvalue(),
    )


def _config_case_matches(result: Any, expected: dict[str, str]) -> bool:
    for field_name, expected_value in expected.items():
        actual_value = getattr(result, field_name)
        if hasattr(actual_value, "value"):
            actual_value = actual_value.value
        elif isinstance(actual_value, Path):
            actual_value = actual_value.as_posix()
        if actual_value != expected_value:
            return False
    return True


def _output_value(output: str, key: str) -> str:
    prefix = f"{key}="
    for line in output.splitlines():
        if line.startswith(prefix):
            return line.split("=", 1)[1]
    return ""


def _evaluate_config_audit() -> _AuditOutcome:
    cases: tuple[tuple[str, dict[str, str], dict[str, Any], dict[str, str]], ...] = (
        ("default_auto", {}, {}, {"resolved_profile": "sqlite_local", "backend": "sqlite"}),
        (
            "default_auto_postgres_env",
            {"MIND_POSTGRES_DSN": "postgresql+psycopg://env-main"},
            {},
            {
                "resolved_profile": "postgres_main",
                "backend": "postgresql",
                "postgres_dsn_source": "env:MIND_POSTGRES_DSN",
            },
        ),
        (
            "default_auto_sqlite_env_path",
            {"MIND_SQLITE_PATH": "/tmp/mind.sqlite3"},
            {},
            {
                "resolved_profile": "sqlite_local",
                "backend": "sqlite",
                "sqlite_path_source": "env:MIND_SQLITE_PATH",
            },
        ),
        (
            "env_profile_sqlite_local",
            {"MIND_CLI_PROFILE": "sqlite_local"},
            {},
            {
                "requested_profile_source": "env:MIND_CLI_PROFILE",
                "resolved_profile": "sqlite_local",
                "backend": "sqlite",
            },
        ),
        (
            "env_profile_postgres_main",
            {
                "MIND_CLI_PROFILE": "postgres_main",
                "MIND_POSTGRES_DSN": "postgresql+psycopg://env-main",
            },
            {},
            {
                "requested_profile_source": "env:MIND_CLI_PROFILE",
                "resolved_profile": "postgres_main",
                "backend": "postgresql",
            },
        ),
        (
            "env_profile_postgres_test",
            {
                "MIND_CLI_PROFILE": "postgres_test",
                "MIND_TEST_POSTGRES_DSN": "postgresql+psycopg://env-test",
            },
            {},
            {
                "requested_profile_source": "env:MIND_CLI_PROFILE",
                "resolved_profile": "postgres_test",
                "postgres_dsn_source": "env:MIND_TEST_POSTGRES_DSN",
            },
        ),
        (
            "cli_profile_beats_env_profile",
            {"MIND_CLI_PROFILE": "postgres_test"},
            {"profile": CliProfile.SQLITE_LOCAL},
            {
                "requested_profile_source": "cli",
                "resolved_profile": "sqlite_local",
                "backend": "sqlite",
            },
        ),
        (
            "cli_profile_postgres_main",
            {
                "MIND_CLI_PROFILE": "sqlite_local",
                "MIND_POSTGRES_DSN": "postgresql+psycopg://env-main",
            },
            {"profile": CliProfile.POSTGRES_MAIN},
            {
                "requested_profile_source": "cli",
                "resolved_profile": "postgres_main",
                "backend": "postgresql",
            },
        ),
        (
            "cli_dsn_overrides_env",
            {"MIND_POSTGRES_DSN": "postgresql+psycopg://env-main"},
            {"profile": CliProfile.POSTGRES_MAIN, "postgres_dsn": "postgresql+psycopg://cli-main"},
            {
                "postgres_dsn_source": "cli",
                "backend": "postgresql",
            },
        ),
        (
            "cli_sqlite_path_overrides_env",
            {"MIND_SQLITE_PATH": "/tmp/env.sqlite3"},
            {"sqlite_path": "/tmp/cli.sqlite3"},
            {
                "sqlite_path_source": "cli",
                "backend": "sqlite",
            },
        ),
        (
            "backend_override_to_postgres",
            {},
            {"backend": CliBackend.POSTGRESQL, "postgres_dsn": "postgresql+psycopg://cli-main"},
            {
                "resolved_profile": "postgres_main",
                "backend": "postgresql",
                "backend_source": "cli",
            },
        ),
        (
            "backend_override_to_sqlite",
            {"MIND_POSTGRES_DSN": "postgresql+psycopg://env-main"},
            {"backend": CliBackend.SQLITE},
            {
                "resolved_profile": "sqlite_local",
                "backend": "sqlite",
                "backend_source": "cli",
            },
        ),
        (
            "postgres_test_profile_uses_test_env",
            {"MIND_TEST_POSTGRES_DSN": "postgresql+psycopg://env-test"},
            {"profile": CliProfile.POSTGRES_TEST},
            {
                "resolved_profile": "postgres_test",
                "postgres_dsn_source": "env:MIND_TEST_POSTGRES_DSN",
            },
        ),
        (
            "postgres_main_missing_dsn",
            {},
            {"profile": CliProfile.POSTGRES_MAIN},
            {
                "resolved_profile": "postgres_main",
                "postgres_dsn_source": "missing:MIND_POSTGRES_DSN",
            },
        ),
        (
            "backend_override_postgres_on_sqlite_profile",
            {},
            {
                "profile": CliProfile.SQLITE_LOCAL,
                "backend": CliBackend.POSTGRESQL,
                "postgres_dsn": "postgresql+psycopg://cli-main",
            },
            {
                "resolved_profile": "sqlite_local",
                "backend": "postgresql",
                "backend_source": "cli",
            },
        ),
        (
            "backend_override_sqlite_on_postgres_profile",
            {"MIND_POSTGRES_DSN": "postgresql+psycopg://env-main"},
            {
                "profile": CliProfile.POSTGRES_MAIN,
                "backend": CliBackend.SQLITE,
            },
            {
                "resolved_profile": "postgres_main",
                "backend": "sqlite",
                "backend_source": "cli",
            },
        ),
        (
            "env_profile_plus_cli_sqlite_path",
            {"MIND_CLI_PROFILE": "sqlite_local"},
            {"sqlite_path": "/tmp/cli-2.sqlite3"},
            {
                "resolved_profile": "sqlite_local",
                "sqlite_path_source": "cli",
            },
        ),
        (
            "env_profile_plus_cli_dsn",
            {
                "MIND_CLI_PROFILE": "postgres_main",
                "MIND_POSTGRES_DSN": "postgresql+psycopg://env-main",
            },
            {"postgres_dsn": "postgresql+psycopg://cli-override"},
            {
                "resolved_profile": "postgres_main",
                "postgres_dsn_source": "cli",
            },
        ),
        (
            "auto_with_backend_override_and_env_profile",
            {"MIND_CLI_PROFILE": "postgres_test"},
            {"backend": CliBackend.SQLITE},
            {
                "requested_profile_source": "env:MIND_CLI_PROFILE",
                "resolved_profile": "postgres_test",
                "backend": "sqlite",
            },
        ),
        (
            "auto_with_backend_override_postgres_and_env_profile",
            {"MIND_CLI_PROFILE": "sqlite_local"},
            {
                "backend": CliBackend.POSTGRESQL,
                "postgres_dsn": "postgresql+psycopg://cli-main",
            },
            {
                "requested_profile_source": "env:MIND_CLI_PROFILE",
                "resolved_profile": "sqlite_local",
                "backend": "postgresql",
            },
        ),
    )

    failures: list[str] = []
    pass_count = 0
    for case_id, env, overrides, expected in cases:
        result = resolve_cli_config(env=env, allow_sqlite=True, **overrides)
        if _config_case_matches(result, expected):
            pass_count += 1
            continue
        failures.append(case_id)

    return _AuditOutcome(pass_count=pass_count, total=len(cases), failures=tuple(failures))


def _evaluate_output_contract_audit() -> _AuditOutcome:
    failures: list[str] = []
    pass_count = 0
    total = 8
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "cli_output.sqlite3"
        plan_db_path = Path(tmpdir) / "cli_output_governance.sqlite3"

        checks: list[tuple[str, _CommandRun, tuple[str, ...]]] = [
            (
                "config_show",
                _invoke_mind(("mind", "config", "show")),
                ("requested_profile=", "backend="),
            ),
        ]

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
                "phase-j-output",
                "--timestamp-order",
                "1",
                "--content",
                "phase j output anchor",
            )
        )
        object_id = _output_value(write.stdout, "object_id")
        checks.append(("primitive_write_raw", write, ("primitive=write_raw", "response_json=")))

        read = _invoke_mind(
            (
                "mind",
                "primitive",
                "read",
                "--sqlite-path",
                str(db_path),
                "--object-id",
                object_id,
            )
        )
        checks.append(("primitive_read", read, ("primitive=read", "response_json=")))

        retrieve = _invoke_mind(
            (
                "mind",
                "primitive",
                "retrieve",
                "--sqlite-path",
                str(db_path),
                "--query",
                "output anchor",
            )
        )
        checks.append(("primitive_retrieve", retrieve, ("primitive=retrieve", "response_json=")))

        access_run = _invoke_mind(
            (
                "mind",
                "access",
                "run",
                "--sqlite-path",
                str(Path(tmpdir) / "cli_access.sqlite3"),
                "--seed-bench-fixtures",
                "--mode",
                "flash",
                "--task-id",
                "x",
                "--episode-id",
                "episode-001",
                "--query",
                "For episode-001, reply with only success or failure.",
            )
        )
        checks.append(("access_run", access_run, ("requested_mode=", "trace_1=")))

        access_benchmark = _invoke_mind(("mind", "access", "benchmark"))
        checks.append(("access_benchmark", access_benchmark, ("frontier_1=", "aggregate_1=")))

        gov_write = _invoke_mind(
            (
                "mind",
                "primitive",
                "write-raw",
                "--sqlite-path",
                str(plan_db_path),
                "--record-kind",
                "user_message",
                "--episode-id",
                "phase-j-governance",
                "--timestamp-order",
                "1",
                "--content",
                "governance preview anchor",
                "--provenance-json",
                '{"producer_kind":"user","producer_id":"cli-user","captured_at":"2026-03-10T12:00:00Z","source_channel":"chat","tenant_id":"tenant-a","user_id":"user-a","episode_id":"phase-j-governance"}',
            )
        )
        if gov_write.exit_code != 0:
            checks.append(("governance_preview", gov_write, ("provenance_summaries_json=",)))
        else:
            plan = _invoke_mind(
                (
                    "mind",
                    "governance",
                    "plan-conceal",
                    "--sqlite-path",
                    str(plan_db_path),
                    "--episode-id",
                    "phase-j-governance",
                    "--reason",
                    "phase j output contract",
                )
            )
            operation_id = _output_value(plan.stdout, "operation_id")
            preview = _invoke_mind(
                (
                    "mind",
                    "governance",
                    "preview",
                    "--sqlite-path",
                    str(plan_db_path),
                    "--operation-id",
                    operation_id,
                )
            )
            checks.append(
                ("governance_preview", preview, ("provenance_summaries_json=", "summary_1="))
            )

        demo = _invoke_mind(("mind", "demo", "ingest-read"))
        checks.append(("demo_ingest_read", demo, ("read_response_json=", "read_object_count=1")))

        for check_id, run, required_fragments in checks:
            if run.exit_code == 0 and all(
                fragment in run.stdout for fragment in required_fragments
            ):
                pass_count += 1
                continue
            failures.append(check_id)

    return _AuditOutcome(pass_count=pass_count, total=total, failures=tuple(failures))
