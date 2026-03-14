"""Deployment smoke suite fixtures and evaluation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .deployment_smoke_helpers import (
    depends_on_healthy,
    dockerfile_ref,
    env_file_ref,
    healthcheck_command,
    load_yaml,
    parse_compose_file,  # noqa: F401
    parse_dockerfile,  # noqa: F401
    parse_dockerfile_instructions,
    postgres_password_ref,
    read_deployment_smoke_report_json,  # noqa: F401
    read_env_var_names,
    read_text,
    render_deployment_smoke_report_markdown,  # noqa: F401
    worker_command,
    write_deployment_smoke_report_json,  # noqa: F401
    write_deployment_smoke_report_markdown,  # noqa: F401
)
from .product_transport_audit import (
    ProductTransportAuditReport,
    evaluate_runtime_product_transport_audit_report,
)

_SCHEMA_VERSION = "deployment_smoke_report_v1"
_SUITE_VERSION = "DeploymentSmokeSuite v1"


@dataclass(frozen=True)
class DeploymentSmokeScenario:
    """One deployment smoke validation scenario."""

    name: str
    description: str


@dataclass(frozen=True)
class DeploymentSmokeResult:
    """Outcome of one smoke validation scenario."""

    name: str
    description: str
    passed: bool


@dataclass(frozen=True)
class DeploymentSmokeReport:
    """Aggregated smoke suite report."""

    schema_version: str
    generated_at: str
    suite_version: str
    results: tuple[DeploymentSmokeResult, ...]

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        passed = sum(1 for result in self.results if result.passed)
        return passed / len(self.results)

    @property
    def scenario_count(self) -> int:
        return len(self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for result in self.results if result.passed)

    @property
    def failure_ids(self) -> tuple[str, ...]:
        return tuple(result.name for result in self.results if not result.passed)

    @property
    def passed(self) -> bool:
        return self.passed_count == self.scenario_count


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
        DeploymentSmokeScenario("dev_api_mounts_frontend", "dev api mounts frontend assets"),
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
        DeploymentSmokeScenario(
            "dockerfile_api_installs_api",
            "Dockerfile.api installs the api dependency set",
        ),
        DeploymentSmokeScenario(
            "dockerfile_api_bundles_frontend",
            "Dockerfile.api copies frontend static assets into the image",
        ),
        DeploymentSmokeScenario(
            "dockerfile_api_uses_pip_cache_mount",
            "Dockerfile.api uses a BuildKit pip cache mount",
        ),
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
        DeploymentSmokeScenario(
            "dockerfile_worker_uses_pip_cache_mount",
            "Dockerfile.worker uses a BuildKit pip cache mount",
        ),
        DeploymentSmokeScenario(
            "dockerfile_docs_dev_uses_pip_cache_mount",
            "Dockerfile.docs.dev uses a BuildKit pip cache mount",
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
        DeploymentSmokeScenario(
            "runtime_product_transport_coverage",
            "runtime product transport audit coverage satisfies the deployment floor",
        ),
        DeploymentSmokeScenario(
            "runtime_product_transport_rest_mcp",
            "runtime REST and MCP transports stay consistent in the frozen audit",
        ),
        DeploymentSmokeScenario(
            "runtime_product_transport_rest_cli",
            "runtime REST and product CLI transports stay consistent in the frozen audit",
        ),
    )


def evaluate_deployment_smoke_suite(
    root: Path,
    *,
    runtime_product_transport_report: ProductTransportAuditReport | None = None,
    generated_at: datetime | None = None,
) -> DeploymentSmokeReport:
    """Evaluate the deployment smoke suite against the repository root."""

    compose_data = load_yaml(root / "compose.yaml")
    compose_dev_data = load_yaml(root / "compose.dev.yaml")
    compose_docs_data = load_yaml(root / "compose.docs.yaml")
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
    dev_docs = (
        compose_dev_services.get("docs", {}) if isinstance(compose_dev_services, dict) else {}
    )
    docs = compose_docs_services.get("docs", {}) if isinstance(compose_docs_services, dict) else {}
    dockerfile_api = root / "Dockerfile.api"
    dockerfile_docs = root / "Dockerfile.docs"
    dockerfile_docs_dev = root / "Dockerfile.docs.dev"
    dockerfile_worker = root / "Dockerfile.worker"
    env_example = root / ".env.example"
    entrypoint = root / "scripts" / "entrypoint-api.sh"
    api_instructions = parse_dockerfile_instructions(dockerfile_api)
    docs_instructions = parse_dockerfile_instructions(dockerfile_docs)
    docs_dev_instructions = parse_dockerfile_instructions(dockerfile_docs_dev)
    parse_dockerfile_instructions(dockerfile_worker)
    env_vars = read_env_var_names(env_example)
    runtime_product_transport_checks = _build_runtime_product_transport_checks(
        runtime_product_transport_report
    )

    checks: dict[str, bool] = {
        "compose_exists": (root / "compose.yaml").exists(),
        "compose_has_postgres": "postgres" in compose_services,
        "compose_has_api": "api" in compose_services,
        "compose_has_worker": "worker" in compose_services,
        "compose_has_named_volume": "postgres_data" in compose_volumes,
        "compose_docs_exists": (root / "compose.docs.yaml").exists(),
        "compose_docs_has_service": "docs" in compose_docs_services,
        "compose_dev_has_docs_service": "docs" in compose_dev_services,
        "compose_uses_runtime_env_file": env_file_ref(api) == "${MIND_ENV_FILE:-.env}"
        and env_file_ref(worker) == "${MIND_ENV_FILE:-.env}",
        "postgres_healthcheck": bool(postgres.get("healthcheck")),
        "postgres_uses_configured_password": postgres_password_ref(postgres)
        == "${MIND_POSTGRES_PASSWORD:-postgres}",
        "api_healthcheck": bool(api.get("healthcheck")),
        "api_healthcheck_endpoint": "/v1/system/health" in healthcheck_command(api),
        "worker_healthcheck": bool(worker.get("healthcheck")),
        "docs_healthcheck": bool(docs.get("healthcheck")),
        "api_depends_on_postgres_healthy": depends_on_healthy(api, "postgres"),
        "worker_depends_on_postgres_healthy": depends_on_healthy(worker, "postgres"),
        "api_builds_dockerfile_api": dockerfile_ref(api) == "Dockerfile.api",
        "docs_builds_dockerfile_docs": dockerfile_ref(docs) == "Dockerfile.docs",
        "worker_builds_dockerfile_worker": dockerfile_ref(worker) == "Dockerfile.worker",
        "api_exposes_18600": "18600:18600" in list(api.get("ports", [])),
        "dev_api_mounts_frontend": any(
            "frontend" in str(volume)
            for volume in list(compose_dev_services.get("api", {}).get("volumes", []))
        ),
        "docs_exposes_18601": any("18601" in str(port) for port in list(docs.get("ports", []))),
        "dev_docs_exposes_18602": any(
            "18602" in str(port) for port in list(dev_docs.get("ports", []))
        ),
        "postgres_exposes_18605": any(
            "18605:5432" in str(port) for port in list(postgres.get("ports", []))
        ),
        "dev_api_debugpy_exposes_18606": any(
            "18606:5678" in str(port) for port in list(api.get("ports", []))
        )
        or any(
            "18606:5678" in str(port)
            for port in list(compose_dev_services.get("api", {}).get("ports", []))
        ),
        "worker_runs_loop": "mindtest-offline-worker-once" in worker_command(worker),
        "dockerfile_api_exists": dockerfile_api.exists(),
        "dockerfile_api_installs_api": "requirements-api.txt" in read_text(dockerfile_api)
        and "optional-dependencies" in read_text(dockerfile_api)
        and '.get("api", [])' in read_text(dockerfile_api),
        "dockerfile_api_bundles_frontend": any(
            line.startswith("COPY frontend ") for line in api_instructions
        ),
        "dockerfile_api_uses_pip_cache_mount": "--mount=type=cache,target=/root/.cache/pip"
        in read_text(dockerfile_api),
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
        "dockerfile_worker_installs_project": "pip install --no-build-isolation --no-deps ."
        in read_text(dockerfile_worker),
        "dockerfile_worker_uses_pip_cache_mount": "--mount=type=cache,target=/root/.cache/pip"
        in read_text(dockerfile_worker),
        "dockerfile_docs_dev_uses_pip_cache_mount": "--mount=type=cache,target=/root/.cache/pip"
        in read_text(dockerfile_docs_dev),
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
        "entrypoint_runs_migration": "alembic upgrade head" in read_text(entrypoint),
        "entrypoint_runs_uvicorn": "uvicorn mind.api.app:create_app --factory"
        in read_text(entrypoint),
        "deploy_script_builds_docs_site": "build_docs_site"
        in read_text(root / "scripts" / "deploy.sh")
        and "mkdocs build --strict" in read_text(root / "scripts" / "deploy.sh"),
        "deploy_script_includes_docs_overlay": 'DOCS_FILE="compose.docs.yaml"'
        in read_text(root / "scripts" / "deploy.sh"),
        **runtime_product_transport_checks,
    }

    results = tuple(
        DeploymentSmokeResult(
            name=scenario.name,
            description=scenario.description,
            passed=checks.get(scenario.name, False),
        )
        for scenario in build_deployment_smoke_suite_v1()
    )
    return DeploymentSmokeReport(
        schema_version=_SCHEMA_VERSION,
        generated_at=(generated_at or datetime.now(UTC)).isoformat(),
        suite_version=_SUITE_VERSION,
        results=results,
    )


def _build_runtime_product_transport_checks(
    report: ProductTransportAuditReport | None = None,
) -> dict[str, bool]:
    runtime_report = report
    if runtime_report is None:
        try:
            runtime_report = evaluate_runtime_product_transport_audit_report()
        except Exception:
            return {
                "runtime_product_transport_coverage": False,
                "runtime_product_transport_rest_mcp": False,
                "runtime_product_transport_rest_cli": False,
            }

    return {
        "runtime_product_transport_coverage": runtime_report.coverage >= 0.95,
        "runtime_product_transport_rest_mcp": runtime_report.rest_mcp_pass_rate >= 0.95,
        "runtime_product_transport_rest_cli": runtime_report.rest_cli_pass_rate >= 0.95,
    }
