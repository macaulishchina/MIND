from __future__ import annotations

from pathlib import Path

from mind.cli_config import (
    CliBackend,
    CliProfile,
    build_config_doctor_checks,
    list_cli_profiles,
    redact_dsn,
    resolve_cli_config,
)


def test_auto_profile_defaults_to_sqlite_without_postgres_env() -> None:
    resolved = resolve_cli_config(env={})

    assert resolved.requested_profile is CliProfile.AUTO
    assert resolved.resolved_profile is CliProfile.SQLITE_LOCAL
    assert resolved.backend is CliBackend.SQLITE
    assert resolved.sqlite_path == Path("artifacts/dev/mind.sqlite3")
    assert resolved.sqlite_path_source == "default"
    assert resolved.postgres_dsn is None


def test_auto_profile_prefers_postgres_when_main_dsn_exists() -> None:
    resolved = resolve_cli_config(env={"MIND_POSTGRES_DSN": "postgresql+psycopg://postgres"})

    assert resolved.resolved_profile is CliProfile.POSTGRES_MAIN
    assert resolved.backend is CliBackend.POSTGRESQL
    assert resolved.postgres_dsn == "postgresql+psycopg://postgres"
    assert resolved.postgres_dsn_source == "env:MIND_POSTGRES_DSN"


def test_cli_profile_override_beats_environment_profile() -> None:
    resolved = resolve_cli_config(
        profile="sqlite_local",
        env={
            "MIND_CLI_PROFILE": "postgres_test",
            "MIND_TEST_POSTGRES_DSN": "postgresql+psycopg://test",
        },
    )

    assert resolved.requested_profile is CliProfile.SQLITE_LOCAL
    assert resolved.requested_profile_source == "cli"
    assert resolved.resolved_profile is CliProfile.SQLITE_LOCAL
    assert resolved.backend is CliBackend.SQLITE


def test_postgres_test_profile_uses_test_dsn_env() -> None:
    resolved = resolve_cli_config(
        profile="postgres_test",
        env={"MIND_TEST_POSTGRES_DSN": "postgresql+psycopg://pytest"},
    )

    assert resolved.resolved_profile is CliProfile.POSTGRES_TEST
    assert resolved.backend is CliBackend.POSTGRESQL
    assert resolved.postgres_dsn == "postgresql+psycopg://pytest"
    assert resolved.postgres_dsn_source == "env:MIND_TEST_POSTGRES_DSN"


def test_backend_override_to_postgres_uses_cli_dsn() -> None:
    resolved = resolve_cli_config(
        profile="sqlite_local",
        backend="postgresql",
        postgres_dsn="postgresql+psycopg://override",
        env={},
    )

    assert resolved.resolved_profile is CliProfile.SQLITE_LOCAL
    assert resolved.backend is CliBackend.POSTGRESQL
    assert resolved.backend_source == "cli"
    assert resolved.postgres_dsn == "postgresql+psycopg://override"
    assert resolved.postgres_dsn_source == "cli"


def test_config_doctor_warns_when_postgres_dsn_missing() -> None:
    resolved = resolve_cli_config(profile="postgres_main", env={})
    checks = build_config_doctor_checks(resolved)

    assert checks[-1].name == "postgres_dsn"
    assert checks[-1].status == "warn"
    assert checks[-1].detail == "missing:MIND_POSTGRES_DSN"


def test_profile_catalog_is_frozen() -> None:
    profiles = list_cli_profiles()

    assert [profile.profile.value for profile in profiles] == [
        "auto",
        "sqlite_local",
        "postgres_main",
        "postgres_test",
    ]


def test_redact_dsn_masks_password() -> None:
    redacted = redact_dsn("postgresql+psycopg://user:secret@127.0.0.1:5432/postgres")

    assert redacted == "postgresql+psycopg://user:***@127.0.0.1:5432/postgres"
