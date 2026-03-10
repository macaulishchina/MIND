"""Unified CLI configuration helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from os import environ
from pathlib import Path
from urllib.parse import SplitResult, urlsplit, urlunsplit


class CliBackend(StrEnum):
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


class CliProfile(StrEnum):
    AUTO = "auto"
    SQLITE_LOCAL = "sqlite_local"
    POSTGRES_MAIN = "postgres_main"
    POSTGRES_TEST = "postgres_test"


@dataclass(frozen=True)
class CliProfileSpec:
    profile: CliProfile
    description: str
    default_backend: CliBackend
    env_hint: str | None


@dataclass(frozen=True)
class ResolvedCliConfig:
    requested_profile: CliProfile
    requested_profile_source: str
    resolved_profile: CliProfile
    backend: CliBackend
    backend_source: str
    sqlite_path: Path | None
    sqlite_path_source: str | None
    postgres_dsn: str | None
    postgres_dsn_source: str | None


@dataclass(frozen=True)
class ConfigDoctorCheck:
    name: str
    status: str
    detail: str


DEFAULT_SQLITE_PATH = Path("artifacts/dev/mind.sqlite3")

_PROFILE_SPECS: tuple[CliProfileSpec, ...] = (
    CliProfileSpec(
        profile=CliProfile.AUTO,
        description=(
            "Default CLI profile. Prefer PostgreSQL when MIND_POSTGRES_DSN is set; "
            "otherwise fall back to the local SQLite reference path."
        ),
        default_backend=CliBackend.SQLITE,
        env_hint=None,
    ),
    CliProfileSpec(
        profile=CliProfile.SQLITE_LOCAL,
        description=(
            "Local SQLite profile for fast development, tests, and reference-backend runs."
        ),
        default_backend=CliBackend.SQLITE,
        env_hint="MIND_SQLITE_PATH",
    ),
    CliProfileSpec(
        profile=CliProfile.POSTGRES_MAIN,
        description=(
            "Primary PostgreSQL profile for the formal backend and worker flows."
        ),
        default_backend=CliBackend.POSTGRESQL,
        env_hint="MIND_POSTGRES_DSN",
    ),
    CliProfileSpec(
        profile=CliProfile.POSTGRES_TEST,
        description=(
            "PostgreSQL test profile for isolated regression or temporary database runs."
        ),
        default_backend=CliBackend.POSTGRESQL,
        env_hint="MIND_TEST_POSTGRES_DSN",
    ),
)


def list_cli_profiles() -> tuple[CliProfileSpec, ...]:
    """Return the frozen CLI profile catalog."""

    return _PROFILE_SPECS


def resolve_cli_config(
    *,
    profile: CliProfile | str | None = None,
    backend: CliBackend | str | None = None,
    sqlite_path: str | Path | None = None,
    postgres_dsn: str | None = None,
    env: Mapping[str, str] | None = None,
) -> ResolvedCliConfig:
    """Resolve the active CLI configuration from CLI overrides and environment."""

    active_env = env or environ
    requested_profile, requested_profile_source = _resolve_requested_profile(profile, active_env)
    backend_override = _coerce_backend(backend)
    resolved_profile = _resolve_profile(requested_profile, backend_override, active_env)
    resolved_backend = backend_override or _profile_spec(resolved_profile).default_backend
    backend_source = (
        "cli" if backend_override is not None else f"profile:{resolved_profile.value}"
    )

    resolved_sqlite_path: Path | None = None
    sqlite_path_source: str | None = None
    if resolved_backend is CliBackend.SQLITE:
        if sqlite_path is not None:
            resolved_sqlite_path = Path(sqlite_path)
            sqlite_path_source = "cli"
        elif active_env.get("MIND_SQLITE_PATH"):
            resolved_sqlite_path = Path(active_env["MIND_SQLITE_PATH"])
            sqlite_path_source = "env:MIND_SQLITE_PATH"
        else:
            resolved_sqlite_path = DEFAULT_SQLITE_PATH
            sqlite_path_source = "default"

    resolved_postgres_dsn: str | None = None
    postgres_dsn_source: str | None = None
    if resolved_backend is CliBackend.POSTGRESQL:
        if postgres_dsn is not None:
            resolved_postgres_dsn = postgres_dsn
            postgres_dsn_source = "cli"
        else:
            dsn_env_var = _dsn_env_var_for_profile(resolved_profile)
            env_value = active_env.get(dsn_env_var)
            if env_value:
                resolved_postgres_dsn = env_value
                postgres_dsn_source = f"env:{dsn_env_var}"
            else:
                postgres_dsn_source = f"missing:{dsn_env_var}"

    return ResolvedCliConfig(
        requested_profile=requested_profile,
        requested_profile_source=requested_profile_source,
        resolved_profile=resolved_profile,
        backend=resolved_backend,
        backend_source=backend_source,
        sqlite_path=resolved_sqlite_path,
        sqlite_path_source=sqlite_path_source,
        postgres_dsn=resolved_postgres_dsn,
        postgres_dsn_source=postgres_dsn_source,
    )


def build_config_doctor_checks(config: ResolvedCliConfig) -> tuple[ConfigDoctorCheck, ...]:
    """Return diagnostic checks for the resolved CLI config."""

    checks = [
        ConfigDoctorCheck(
            name="profile_resolution",
            status="ok",
            detail=(
                f"requested={config.requested_profile.value},"
                f"resolved={config.resolved_profile.value},"
                f"source={config.requested_profile_source}"
            ),
        ),
        ConfigDoctorCheck(
            name="backend",
            status="ok",
            detail=f"backend={config.backend.value},source={config.backend_source}",
        ),
    ]

    if config.backend is CliBackend.SQLITE:
        assert config.sqlite_path is not None
        assert config.sqlite_path_source is not None
        checks.append(
            ConfigDoctorCheck(
                name="sqlite_path",
                status="ok",
                detail=(
                    f"path={config.sqlite_path.as_posix()},"
                    f"source={config.sqlite_path_source}"
                ),
            )
        )
    else:
        assert config.postgres_dsn_source is not None
        if config.postgres_dsn is None:
            checks.append(
                ConfigDoctorCheck(
                    name="postgres_dsn",
                    status="warn",
                    detail=config.postgres_dsn_source,
                )
            )
        else:
            status = "ok" if config.postgres_dsn.startswith("postgresql+psycopg://") else "warn"
            detail = (
                f"dsn={redact_dsn(config.postgres_dsn)},"
                f"source={config.postgres_dsn_source}"
            )
            checks.append(ConfigDoctorCheck(name="postgres_dsn", status=status, detail=detail))

    return tuple(checks)


def redact_dsn(dsn: str) -> str:
    """Return a password-redacted DSN for CLI output."""

    parts = urlsplit(dsn)
    if not parts.username and not parts.password:
        return dsn

    hostname = parts.hostname or ""
    port = f":{parts.port}" if parts.port is not None else ""
    username = parts.username or ""
    userinfo = username
    if parts.password is not None:
        userinfo = f"{userinfo}:***"
    netloc = f"{userinfo}@{hostname}{port}" if userinfo else f"{hostname}{port}"
    return urlunsplit(
        SplitResult(
            scheme=parts.scheme,
            netloc=netloc,
            path=parts.path,
            query=parts.query,
            fragment=parts.fragment,
        )
    )


def _profile_spec(profile: CliProfile) -> CliProfileSpec:
    for spec in _PROFILE_SPECS:
        if spec.profile is profile:
            return spec
    raise RuntimeError(f"unknown CLI profile '{profile.value}'")


def _resolve_requested_profile(
    profile: CliProfile | str | None,
    env: Mapping[str, str],
) -> tuple[CliProfile, str]:
    if profile is not None:
        return _coerce_profile(profile), "cli"
    env_profile = env.get("MIND_CLI_PROFILE")
    if env_profile:
        return CliProfile(env_profile), "env:MIND_CLI_PROFILE"
    return CliProfile.AUTO, "default"


def _resolve_profile(
    requested_profile: CliProfile,
    backend_override: CliBackend | None,
    env: Mapping[str, str],
) -> CliProfile:
    if requested_profile is not CliProfile.AUTO:
        return requested_profile
    if backend_override is CliBackend.SQLITE:
        return CliProfile.SQLITE_LOCAL
    if backend_override is CliBackend.POSTGRESQL:
        return CliProfile.POSTGRES_MAIN
    if env.get("MIND_POSTGRES_DSN"):
        return CliProfile.POSTGRES_MAIN
    return CliProfile.SQLITE_LOCAL


def _dsn_env_var_for_profile(profile: CliProfile) -> str:
    if profile is CliProfile.POSTGRES_TEST:
        return "MIND_TEST_POSTGRES_DSN"
    return "MIND_POSTGRES_DSN"


def _coerce_profile(profile: CliProfile | str) -> CliProfile:
    return profile if isinstance(profile, CliProfile) else CliProfile(profile)


def _coerce_backend(backend: CliBackend | str | None) -> CliBackend | None:
    if backend is None:
        return None
    return backend if isinstance(backend, CliBackend) else CliBackend(backend)
