"""Deployment smoke report I/O, parsers, and compose-inspection helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


def write_deployment_smoke_report_json(
    path: str | Path,
    report: Any,
) -> Path:
    """Persist the full deployment smoke report as JSON."""


    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_report_to_dict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def render_deployment_smoke_report_markdown(
    report: Any,
    *,
    title: str = "Deployment Smoke Report",
) -> str:
    """Render the deployment smoke report as Markdown."""

    lines = [
        f"# {title}",
        "",
        f"- Generated at: `{report.generated_at}`",
        f"- Suite version: `{report.suite_version}`",
        f"- Status: `{'PASS' if report.passed else 'FAIL'}`",
        f"- Pass rate: `{report.passed_count}/{report.scenario_count}` (`{report.pass_rate:.4f}`)",
        "",
        "| Scenario | Status | Description |",
        "| --- | --- | --- |",
    ]
    for result in report.results:
        lines.append(
            f"| {result.name} | {'PASS' if result.passed else 'FAIL'} | {result.description} |"
        )
    if report.failure_ids:
        lines.extend(
            [
                "",
                f"Failing scenarios: `{','.join(report.failure_ids)}`",
            ]
        )
    return "\n".join(lines) + "\n"


def write_deployment_smoke_report_markdown(
    path: str | Path,
    report: Any,
    *,
    title: str = "Deployment Smoke Report",
) -> Path:
    """Persist the deployment smoke report as Markdown."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_deployment_smoke_report_markdown(report, title=title),
        encoding="utf-8",
    )
    return output_path


def read_deployment_smoke_report_json(path: str | Path) -> Any:
    """Load a previously persisted deployment smoke report."""

    from .deployment_smoke_suite import _SCHEMA_VERSION

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError(
            f"unexpected deployment smoke report schema_version "
            f"({payload.get('schema_version')!r})"
        )
    return _report_from_dict(payload)


def parse_compose_file(path: Path) -> dict[str, Any]:
    """Parse compose.yaml into a dictionary."""

    data = load_yaml(path)
    if not isinstance(data, dict):
        raise ValueError("compose.yaml must parse to a mapping")
    return data


def parse_dockerfile(path: Path) -> list[str]:
    """Return normalized Dockerfile instruction lines."""

    return parse_dockerfile_instructions(path)


def load_yaml(path: Path) -> Any:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def parse_dockerfile_instructions(path: Path) -> list[str]:
    if not path.exists():
        return []
    instructions: list[str] = []
    buffer = ""
    heredoc_terminator: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if heredoc_terminator is not None:
            if stripped == heredoc_terminator:
                heredoc_terminator = None
            continue
        if not stripped or stripped.startswith("#"):
            continue

        if buffer:
            buffer = f"{buffer} {stripped}"
        else:
            buffer = stripped

        if "<<" in stripped:
            marker = stripped.split("<<", 1)[1].strip()
            heredoc_terminator = marker.strip("'\"")

        if buffer.endswith("\\"):
            buffer = buffer[:-1].rstrip()
            continue

        instructions.append(buffer)
        buffer = ""

    if buffer:
        instructions.append(buffer)
    return instructions


def read_env_var_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    env_vars: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        env_vars.add(stripped.split("=", 1)[0])
    return env_vars


def depends_on_healthy(service: dict[str, Any], dependency: str) -> bool:
    depends_on = service.get("depends_on", {})
    if not isinstance(depends_on, dict):
        return False
    dependency_config = depends_on.get(dependency, {})
    if not isinstance(dependency_config, dict):
        return False
    return dependency_config.get("condition") == "service_healthy"


def dockerfile_ref(service: dict[str, Any]) -> str | None:
    build = service.get("build", {})
    if not isinstance(build, dict):
        return None
    dockerfile = build.get("dockerfile")
    return str(dockerfile) if dockerfile is not None else None


def env_file_ref(service: dict[str, Any]) -> str | None:
    env_file = service.get("env_file")
    if isinstance(env_file, list) and env_file:
        return str(env_file[0])
    if isinstance(env_file, str):
        return env_file
    return None


def worker_command(service: dict[str, Any]) -> str:
    command = service.get("command", [])
    if isinstance(command, list):
        return "\n".join(str(part) for part in command)
    return str(command)


def healthcheck_command(service: dict[str, Any]) -> str:
    healthcheck = service.get("healthcheck", {})
    if not isinstance(healthcheck, dict):
        return ""
    test = healthcheck.get("test", [])
    if isinstance(test, list):
        return "\n".join(str(part) for part in test)
    return str(test)


def postgres_password_ref(service: dict[str, Any]) -> str | None:
    environment = service.get("environment", {})
    if not isinstance(environment, dict):
        return None
    password = environment.get("POSTGRES_PASSWORD")
    return str(password) if password is not None else None


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _report_to_dict(report: Any) -> dict[str, Any]:
    return {
        "schema_version": report.schema_version,
        "generated_at": report.generated_at,
        "suite_version": report.suite_version,
        "scenario_count": report.scenario_count,
        "passed_count": report.passed_count,
        "pass_rate": report.pass_rate,
        "passed": report.passed,
        "failure_ids": list(report.failure_ids),
        "results": [
            {
                "name": result.name,
                "description": result.description,
                "passed": result.passed,
            }
            for result in report.results
        ],
    }


def _report_from_dict(payload: dict[str, Any]) -> Any:
    from .deployment_smoke_suite import DeploymentSmokeReport, DeploymentSmokeResult

    return DeploymentSmokeReport(
        schema_version=str(payload["schema_version"]),
        generated_at=str(payload["generated_at"]),
        suite_version=str(payload["suite_version"]),
        results=tuple(
            DeploymentSmokeResult(
                name=str(result["name"]),
                description=str(result["description"]),
                passed=bool(result["passed"]),
            )
            for result in payload.get("results", [])
        ),
    )
