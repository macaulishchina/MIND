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
        DeploymentSmokeScenario("compose_docs_exists", "compose.docs.yaml exists"),
        DeploymentSmokeScenario("compose_docs_has_service", "compose.docs defines docs service"),
        DeploymentSmokeScenario("compose_dev_has_docs_service", "compose.dev defines docs service"),
        DeploymentSmokeScenario(
            "compose_uses_runtime_env_file",
            "api and worker load the runtime env file selected by scripts",
        ),
        DeploymentSmokeScenario("postgres_healthcheck", "postgres has healthcheck"),
        DeploymentSmokeScenario(
            "postgres_uses_configured_password",
            "postgres password comes from env configuration",
        ),
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
        DeploymentSmokeScenario("api_exposes_18600", "api publishes port 18600"),
        DeploymentSmokeScenario("worker_runs_loop", "worker command loops the offline worker"),
        DeploymentSmokeScenario("docs_healthcheck", "docs service has healthcheck"),
        DeploymentSmokeScenario("docs_builds_dockerfile_docs", "docs uses Dockerfile.docs"),
        DeploymentSmokeScenario("docs_exposes_18601", "docs publishes port 18601"),
        DeploymentSmokeScenario("dev_docs_exposes_18602", "dev docs publishes port 18602"),
        DeploymentSmokeScenario("postgres_exposes_18605", "postgres publishes port 18605"),
        DeploymentSmokeScenario(
            "dev_api_debugpy_exposes_18606",
            "dev api publishes debugpy host port 18606",
        ),
        DeploymentSmokeScenario("dockerfile_api_exists", "Dockerfile.api exists"),
        DeploymentSmokeScenario("dockerfile_api_installs_api", "Dockerfile.api installs .[api]"),
        DeploymentSmokeScenario(
            "dockerfile_api_entrypoint",
            "Dockerfile.api uses entrypoint script",
        ),
        DeploymentSmokeScenario("dockerfile_docs_exists", "Dockerfile.docs exists"),
        DeploymentSmokeScenario("dockerfile_docs_builds_site", "Dockerfile.docs serves built site"),
        DeploymentSmokeScenario("dockerfile_docs_dev_exists", "Dockerfile.docs.dev exists"),
        DeploymentSmokeScenario(
            "dockerfile_docs_dev_serves_mkdocs",
            "Dockerfile.docs.dev launches mkdocs serve",
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
        DeploymentSmokeScenario(
            "deploy_script_builds_docs_site",
            "deploy script builds docs site before production compose up",
        ),
        DeploymentSmokeScenario(
            "deploy_script_includes_docs_overlay",
            "deploy script includes compose.docs.yaml in production deploy",
        ),
    )


def evaluate_deployment_smoke_suite(root: Path) -> DeploymentSmokeReport:
    """Evaluate the deployment smoke suite against the repository root."""

    compose_data = _load_yaml(root / "compose.yaml")
    compose_dev_data = _load_yaml(root / "compose.dev.yaml")
    compose_docs_data = _load_yaml(root / "compose.docs.yaml")
    compose_services = compose_data.get("services", {}) if isinstance(compose_data, dict) else {}
    compose_dev_services = (
        compose_dev_data.get("services", {}) if isinstance(compose_dev_data, dict) else {}
    )
    compose_docs_services = (
        compose_docs_data.get("services", {}) if isinstance(compose_docs_data, dict) else {}
    )
    compose_volumes = compose_data.get("volumes", {}) if isinstance(compose_data, dict) else {}
    postgres = compose_services.get("postgres", {}) if isinstance(compose_services, dict) else {}
    api = compose_services.get("api", {}) if isinstance(compose_services, dict) else {}
    worker = compose_services.get("worker", {}) if isinstance(compose_services, dict) else {}
    dev_docs = compose_dev_services.get("docs", {}) if isinstance(compose_dev_services, dict) else {}
    docs = compose_docs_services.get("docs", {}) if isinstance(compose_docs_services, dict) else {}
    dockerfile_api = root / "Dockerfile.api"
    dockerfile_docs = root / "Dockerfile.docs"
    dockerfile_docs_dev = root / "Dockerfile.docs.dev"
    dockerfile_worker = root / "Dockerfile.worker"
    env_example = root / ".env.example"
    entrypoint = root / "scripts" / "entrypoint-api.sh"
    api_instructions = _parse_dockerfile_instructions(dockerfile_api)
    docs_instructions = _parse_dockerfile_instructions(dockerfile_docs)
    docs_dev_instructions = _parse_dockerfile_instructions(dockerfile_docs_dev)
    worker_instructions = _parse_dockerfile_instructions(dockerfile_worker)
    env_vars = _read_env_var_names(env_example)

    checks: dict[str, bool] = {
        "compose_exists": (root / "compose.yaml").exists(),
        "compose_has_postgres": "postgres" in compose_services,
        "compose_has_api": "api" in compose_services,
        "compose_has_worker": "worker" in compose_services,
        "compose_has_named_volume": "postgres_data" in compose_volumes,
        "compose_docs_exists": (root / "compose.docs.yaml").exists(),
        "compose_docs_has_service": "docs" in compose_docs_services,
        "compose_dev_has_docs_service": "docs" in compose_dev_services,
        "compose_uses_runtime_env_file": _env_file_ref(api) == "${MIND_ENV_FILE:-.env}"
        and _env_file_ref(worker) == "${MIND_ENV_FILE:-.env}",
        "postgres_healthcheck": bool(postgres.get("healthcheck")),
        "postgres_uses_configured_password": _postgres_password_ref(postgres)
        == "${MIND_POSTGRES_PASSWORD:-postgres}",
        "api_healthcheck": bool(api.get("healthcheck")),
        "api_healthcheck_endpoint": "/v1/system/health" in _healthcheck_command(api),
        "worker_healthcheck": bool(worker.get("healthcheck")),
        "docs_healthcheck": bool(docs.get("healthcheck")),
        "api_depends_on_postgres_healthy": _depends_on_healthy(api, "postgres"),
        "worker_depends_on_postgres_healthy": _depends_on_healthy(worker, "postgres"),
        "api_builds_dockerfile_api": _dockerfile_ref(api) == "Dockerfile.api",
        "docs_builds_dockerfile_docs": _dockerfile_ref(docs) == "Dockerfile.docs",
        "worker_builds_dockerfile_worker": _dockerfile_ref(worker) == "Dockerfile.worker",
        "api_exposes_18600": "18600:18600" in list(api.get("ports", [])),
        "docs_exposes_18601": any("18601" in str(port) for port in list(docs.get("ports", []))),
        "dev_docs_exposes_18602": any(
            "18602" in str(port) for port in list(dev_docs.get("ports", []))
        ),
        "postgres_exposes_18605": any(
            "18605:5432" in str(port) for port in list(postgres.get("ports", []))
        ),
        "dev_api_debugpy_exposes_18606": any(
            "18606:5678" in str(port) for port in list(api.get("ports", []))
        ) or any(
            "18606:5678" in str(port) for port in list(compose_dev_services.get("api", {}).get("ports", []))
        ),
        "worker_runs_loop": "mindtest-offline-worker-once" in _worker_command(worker),
        "dockerfile_api_exists": dockerfile_api.exists(),
        "dockerfile_api_installs_api": any(".[api]" in line for line in api_instructions),
        "dockerfile_api_entrypoint": any(
            "entrypoint-api.sh" in line.lower() for line in api_instructions
        ),
        "dockerfile_docs_exists": dockerfile_docs.exists(),
        "dockerfile_docs_builds_site": any(
            line.startswith("COPY site ") for line in docs_instructions
        )
        and any("nginx" in line.lower() for line in docs_instructions),
        "dockerfile_docs_dev_exists": dockerfile_docs_dev.exists(),
        "dockerfile_docs_dev_serves_mkdocs": any(
            "mkdocs" in line.lower() and "serve" in line.lower() for line in docs_dev_instructions
        ),
        "dockerfile_worker_exists": dockerfile_worker.exists(),
        "dockerfile_worker_installs_project": any(
            "pip install ." in line for line in worker_instructions
        ),
        "env_example_exists": env_example.exists(),
        "env_example_required_vars": {
            "MIND_POSTGRES_USER",
            "MIND_POSTGRES_PASSWORD",
            "MIND_POSTGRES_DB",
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
        "deploy_script_builds_docs_site": "build_docs_site" in _read_text(
            root / "scripts" / "deploy.sh"
        )
        and "mkdocs build --strict" in _read_text(root / "scripts" / "deploy.sh"),
        "deploy_script_includes_docs_overlay": 'DOCS_FILE="compose.docs.yaml"' in _read_text(
            root / "scripts" / "deploy.sh"
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


def _env_file_ref(service: dict[str, Any]) -> str | None:
    env_file = service.get("env_file")
    if isinstance(env_file, list) and env_file:
        return str(env_file[0])
    if isinstance(env_file, str):
        return env_file
    return None


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


def _postgres_password_ref(service: dict[str, Any]) -> str | None:
    environment = service.get("environment", {})
    if not isinstance(environment, dict):
        return None
    password = environment.get("POSTGRES_PASSWORD")
    return str(password) if password is not None else None


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")
