"""Deployment smoke suite fixtures and evaluation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


@dataclass(frozen=True)
class DeploymentSmokeScenario:
    """One deployment smoke validation scenario."""

    name: str
    description: str


@dataclass(frozen=True)
class DeploymentSmokeResult:
    """Outcome of one smoke validation scenario."""

    name: str
    passed: bool


@dataclass(frozen=True)
class DeploymentSmokeReport:
    """Aggregated smoke suite report."""

    results: tuple[DeploymentSmokeResult, ...]

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        passed = sum(1 for result in self.results if result.passed)
        return passed / len(self.results)


def build_deployment_smoke_suite_v1() -> tuple[DeploymentSmokeScenario, ...]:
    """Return the v1 deployment smoke suite."""

    return (
        DeploymentSmokeScenario("compose_exists", "compose.yaml exists"),
        DeploymentSmokeScenario("compose_has_postgres", "compose defines postgres service"),
        DeploymentSmokeScenario("compose_has_api", "compose defines api service"),
        DeploymentSmokeScenario("compose_has_worker", "compose defines worker service"),
        DeploymentSmokeScenario("compose_has_named_volume", "compose defines postgres volume"),
        DeploymentSmokeScenario("postgres_healthcheck", "postgres has healthcheck"),
        DeploymentSmokeScenario("api_healthcheck", "api has healthcheck"),
        DeploymentSmokeScenario(
            "api_healthcheck_endpoint",
            "api healthcheck targets /v1/system/health",
        ),
        DeploymentSmokeScenario("worker_healthcheck", "worker has healthcheck"),
        DeploymentSmokeScenario(
            "api_depends_on_postgres_healthy",
            "api waits for postgres health",
        ),
        DeploymentSmokeScenario(
            "worker_depends_on_postgres_healthy",
            "worker waits for postgres health",
        ),
        DeploymentSmokeScenario("api_builds_dockerfile_api", "api uses Dockerfile.api"),
        DeploymentSmokeScenario("worker_builds_dockerfile_worker", "worker uses Dockerfile.worker"),
        DeploymentSmokeScenario("api_exposes_8000", "api publishes port 8000"),
        DeploymentSmokeScenario("worker_runs_loop", "worker command loops the offline worker"),
        DeploymentSmokeScenario("dockerfile_api_exists", "Dockerfile.api exists"),
        DeploymentSmokeScenario("dockerfile_api_installs_api", "Dockerfile.api installs .[api]"),
        DeploymentSmokeScenario(
            "dockerfile_api_entrypoint",
            "Dockerfile.api uses entrypoint script",
        ),
        DeploymentSmokeScenario("dockerfile_worker_exists", "Dockerfile.worker exists"),
        DeploymentSmokeScenario(
            "dockerfile_worker_installs_project",
            "Dockerfile.worker installs project",
        ),
        DeploymentSmokeScenario("env_example_exists", ".env.example exists"),
        DeploymentSmokeScenario("env_example_required_vars", ".env.example contains required vars"),
        DeploymentSmokeScenario("entrypoint_exists", "entrypoint script exists"),
        DeploymentSmokeScenario(
            "entrypoint_runs_migration",
            "entrypoint runs alembic upgrade head",
        ),
        DeploymentSmokeScenario("entrypoint_runs_uvicorn", "entrypoint launches uvicorn"),
    )


def evaluate_deployment_smoke_suite(root: Path) -> DeploymentSmokeReport:
    """Evaluate the deployment smoke suite against the repository root."""

    compose_data = _load_yaml(root / "compose.yaml")
    compose_services = compose_data.get("services", {}) if isinstance(compose_data, dict) else {}
    compose_volumes = compose_data.get("volumes", {}) if isinstance(compose_data, dict) else {}
    postgres = compose_services.get("postgres", {}) if isinstance(compose_services, dict) else {}
    api = compose_services.get("api", {}) if isinstance(compose_services, dict) else {}
    worker = compose_services.get("worker", {}) if isinstance(compose_services, dict) else {}
    dockerfile_api = root / "Dockerfile.api"
    dockerfile_worker = root / "Dockerfile.worker"
    env_example = root / ".env.example"
    entrypoint = root / "scripts" / "entrypoint-api.sh"
    api_instructions = _parse_dockerfile_instructions(dockerfile_api)
    worker_instructions = _parse_dockerfile_instructions(dockerfile_worker)
    env_vars = _read_env_var_names(env_example)

    checks: dict[str, bool] = {
        "compose_exists": (root / "compose.yaml").exists(),
        "compose_has_postgres": "postgres" in compose_services,
        "compose_has_api": "api" in compose_services,
        "compose_has_worker": "worker" in compose_services,
        "compose_has_named_volume": "postgres_data" in compose_volumes,
        "postgres_healthcheck": bool(postgres.get("healthcheck")),
        "api_healthcheck": bool(api.get("healthcheck")),
        "api_healthcheck_endpoint": "/v1/system/health" in _healthcheck_command(api),
        "worker_healthcheck": bool(worker.get("healthcheck")),
        "api_depends_on_postgres_healthy": _depends_on_healthy(api, "postgres"),
        "worker_depends_on_postgres_healthy": _depends_on_healthy(worker, "postgres"),
        "api_builds_dockerfile_api": _dockerfile_ref(api) == "Dockerfile.api",
        "worker_builds_dockerfile_worker": _dockerfile_ref(worker) == "Dockerfile.worker",
        "api_exposes_8000": "8000:8000" in list(api.get("ports", [])),
        "worker_runs_loop": "mindtest-offline-worker-once" in _worker_command(worker),
        "dockerfile_api_exists": dockerfile_api.exists(),
        "dockerfile_api_installs_api": any(".[api]" in line for line in api_instructions),
        "dockerfile_api_entrypoint": any(
            "entrypoint-api.sh" in line.lower() for line in api_instructions
        ),
        "dockerfile_worker_exists": dockerfile_worker.exists(),
        "dockerfile_worker_installs_project": any(
            "pip install ." in line for line in worker_instructions
        ),
        "env_example_exists": env_example.exists(),
        "env_example_required_vars": {
            "MIND_POSTGRES_DSN",
            "MIND_API_KEY",
            "MIND_PROVIDER",
            "MIND_MODEL",
            "MIND_LOG_LEVEL",
            "MIND_DEV_MODE",
        }.issubset(env_vars),
        "entrypoint_exists": entrypoint.exists(),
        "entrypoint_runs_migration": "alembic upgrade head" in _read_text(entrypoint),
        "entrypoint_runs_uvicorn": "uvicorn mind.api.app:create_app --factory" in _read_text(
            entrypoint
        ),
    }

    results = tuple(
        DeploymentSmokeResult(name=scenario.name, passed=checks.get(scenario.name, False))
        for scenario in build_deployment_smoke_suite_v1()
    )
    return DeploymentSmokeReport(results=results)


def parse_compose_file(path: Path) -> dict[str, Any]:
    """Parse compose.yaml into a dictionary."""

    data = _load_yaml(path)
    if not isinstance(data, dict):
        raise ValueError("compose.yaml must parse to a mapping")
    return data


def parse_dockerfile(path: Path) -> list[str]:
    """Return normalized Dockerfile instruction lines."""

    return _parse_dockerfile_instructions(path)


def _load_yaml(path: Path) -> Any:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _parse_dockerfile_instructions(path: Path) -> list[str]:
    if not path.exists():
        return []
    instructions: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        instructions.append(stripped)
    return instructions


def _read_env_var_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    env_vars: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        env_vars.add(stripped.split("=", 1)[0])
    return env_vars


def _depends_on_healthy(service: dict[str, Any], dependency: str) -> bool:
    depends_on = service.get("depends_on", {})
    if not isinstance(depends_on, dict):
        return False
    dependency_config = depends_on.get(dependency, {})
    if not isinstance(dependency_config, dict):
        return False
    return dependency_config.get("condition") == "service_healthy"


def _dockerfile_ref(service: dict[str, Any]) -> str | None:
    build = service.get("build", {})
    if not isinstance(build, dict):
        return None
    dockerfile = build.get("dockerfile")
    return str(dockerfile) if dockerfile is not None else None


def _worker_command(service: dict[str, Any]) -> str:
    command = service.get("command", [])
    if isinstance(command, list):
        return "\n".join(str(part) for part in command)
    return str(command)


def _healthcheck_command(service: dict[str, Any]) -> str:
    healthcheck = service.get("healthcheck", {})
    if not isinstance(healthcheck, dict):
        return ""
    test = healthcheck.get("test", [])
    if isinstance(test, list):
        return "\n".join(str(part) for part in test)
    return str(test)


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")
