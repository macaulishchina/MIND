"""WP-5 deployment asset verification tests."""

from __future__ import annotations

import os
from pathlib import Path

from mind.fixtures.deployment_smoke_suite import (
    build_deployment_smoke_suite_v1,
    evaluate_deployment_smoke_suite,
    parse_compose_file,
    parse_dockerfile,
)

ROOT = Path(__file__).resolve().parent.parent

_VALID_DOCKERFILE_INSTRUCTIONS = {
    "ADD",
    "ARG",
    "CMD",
    "COPY",
    "ENTRYPOINT",
    "ENV",
    "EXPOSE",
    "FROM",
    "HEALTHCHECK",
    "LABEL",
    "ONBUILD",
    "RUN",
    "SHELL",
    "STOPSIGNAL",
    "USER",
    "VOLUME",
    "WORKDIR",
}


def test_dockerfile_syntax_validation() -> None:
    for dockerfile_name in (
        "Dockerfile.api",
        "Dockerfile.worker",
        "Dockerfile.docs",
        "Dockerfile.docs.dev",
    ):
        instructions = parse_dockerfile(ROOT / dockerfile_name)
        assert instructions
        assert instructions[0].startswith("FROM ")
        for line in instructions:
            keyword = line.split(maxsplit=1)[0].upper()
            assert keyword in _VALID_DOCKERFILE_INSTRUCTIONS


def test_compose_yaml_schema_validation() -> None:
    compose_data = parse_compose_file(ROOT / "compose.yaml")

    assert set(compose_data["services"]) == {"postgres", "api", "worker"}
    assert "postgres_data" in compose_data["volumes"]
    assert compose_data["services"]["api"]["env_file"] == ["${MIND_ENV_FILE:-.env}"]
    assert compose_data["services"]["worker"]["env_file"] == ["${MIND_ENV_FILE:-.env}"]
    assert compose_data["services"]["api"]["build"]["dockerfile"] == "Dockerfile.api"
    assert compose_data["services"]["worker"]["build"]["dockerfile"] == "Dockerfile.worker"
    assert (
        compose_data["services"]["api"]["build"]["args"]["PIP_INDEX_URL"]
        == "${MIND_PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
    )
    assert (
        compose_data["services"]["worker"]["build"]["args"]["PIP_INDEX_URL"]
        == "${MIND_PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
    )
    assert (
        compose_data["services"]["postgres"]["environment"]["POSTGRES_PASSWORD"]
        == "${MIND_POSTGRES_PASSWORD:-postgres}"
    )
    assert (
        compose_data["services"]["api"]["depends_on"]["postgres"]["condition"]
        == "service_healthy"
    )
    assert (
        compose_data["services"]["worker"]["depends_on"]["postgres"]["condition"]
        == "service_healthy"
    )


def test_compose_dev_yaml_exists_and_valid() -> None:
    """compose.dev.yaml must exist and define api/worker/docs dev overrides."""
    compose_dev = parse_compose_file(ROOT / "compose.dev.yaml")
    assert "api" in compose_dev["services"]
    assert "worker" in compose_dev["services"]
    assert "docs" in compose_dev["services"]
    # Dev should mount source code
    api_svc = compose_dev["services"]["api"]
    assert "volumes" in api_svc
    assert any("mind" in v for v in api_svc["volumes"])
    assert any("frontend" in v for v in api_svc["volumes"])

    docs_svc = compose_dev["services"]["docs"]
    assert docs_svc["build"]["dockerfile"] == "Dockerfile.docs.dev"
    assert (
        docs_svc["build"]["args"]["PIP_INDEX_URL"]
        == "${MIND_PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
    )
    assert any("18602" in str(v) for v in docs_svc["ports"])
    assert "healthcheck" in docs_svc
    assert any("18606:5678" in str(v) for v in api_svc["ports"])


def test_compose_prod_yaml_exists_and_valid() -> None:
    """compose.prod.yaml must exist and define resource limits."""
    compose_prod = parse_compose_file(ROOT / "compose.prod.yaml")
    assert "api" in compose_prod["services"]
    assert "worker" in compose_prod["services"]
    assert "postgres" in compose_prod["services"]


def test_compose_docs_yaml_exists_and_valid() -> None:
    """compose.docs.yaml must exist and define the docs service."""
    compose_docs = parse_compose_file(ROOT / "compose.docs.yaml")
    assert "docs" in compose_docs["services"]
    docs_svc = compose_docs["services"]["docs"]
    assert docs_svc["build"]["dockerfile"] == "Dockerfile.docs"
    assert any("18601" in str(v) for v in docs_svc["ports"])
    assert "healthcheck" in docs_svc


def test_compose_runtime_ports_use_mind_1860x_family() -> None:
    compose_data = parse_compose_file(ROOT / "compose.yaml")
    compose_dev = parse_compose_file(ROOT / "compose.dev.yaml")

    postgres_svc = compose_data["services"]["postgres"]
    api_svc = compose_data["services"]["api"]
    dev_api_svc = compose_dev["services"]["api"]

    assert any("18605:5432" in str(v) for v in postgres_svc["ports"])
    assert any("18600:18600" in str(v) for v in api_svc["ports"])
    assert any("18606:5678" in str(v) for v in dev_api_svc["ports"])


def test_env_example_covers_required_vars() -> None:
    env_path = ROOT / ".env.example"
    content = env_path.read_text(encoding="utf-8")

    for env_var in (
        "MIND_POSTGRES_USER",
        "MIND_POSTGRES_PASSWORD",
        "MIND_POSTGRES_DB",
        "MIND_POSTGRES_DSN",
        "MIND_API_KEY",
        "MIND_PROVIDER",
        "MIND_MODEL",
        "MIND_DOCS_BIND",
        "MIND_LOG_LEVEL",
        "MIND_DEV_MODE",
        "MIND_PIP_INDEX_URL",
        "MIND_PIP_EXTRA_INDEX_URL",
        "MIND_PIP_TRUSTED_HOST",
    ):
        assert f"{env_var}=" in content


def test_env_dev_covers_required_vars() -> None:
    """`.env.dev` must include all required variables with dev defaults."""
    env_path = ROOT / ".env.dev"
    content = env_path.read_text(encoding="utf-8")

    for env_var in (
        "MIND_POSTGRES_USER",
        "MIND_POSTGRES_PASSWORD",
        "MIND_POSTGRES_DB",
        "MIND_POSTGRES_DSN",
        "MIND_API_KEY",
        "MIND_DOCS_BIND",
        "MIND_LOG_LEVEL",
        "MIND_DEV_MODE",
        "MIND_PIP_INDEX_URL",
        "MIND_PIP_EXTRA_INDEX_URL",
        "MIND_PIP_TRUSTED_HOST",
    ):
        assert f"{env_var}=" in content

    assert "DEBUG" in content
    assert "true" in content.lower()
    assert "MIND_POSTGRES_PASSWORD=postgres" in content
    assert "MIND_API_BIND=0.0.0.0:18600" in content
    assert "MIND_DOCS_BIND=0.0.0.0:18602" in content
    assert "MIND_PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple" in content
    assert "MIND_PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn" in content


def test_env_prod_covers_required_vars() -> None:
    """`.env.prod` must include all required variables with prod defaults."""
    env_path = ROOT / ".env.prod"
    content = env_path.read_text(encoding="utf-8")

    for env_var in (
        "MIND_POSTGRES_USER",
        "MIND_POSTGRES_PASSWORD",
        "MIND_POSTGRES_DB",
        "MIND_POSTGRES_DSN",
        "MIND_API_KEY",
        "MIND_DOCS_BIND",
        "MIND_LOG_LEVEL",
        "MIND_DEV_MODE",
        "MIND_PIP_INDEX_URL",
        "MIND_PIP_EXTRA_INDEX_URL",
        "MIND_PIP_TRUSTED_HOST",
    ):
        assert f"{env_var}=" in content

    assert "WARNING" in content
    assert "MIND_POSTGRES_PASSWORD=CHANGE_ME" in content
    assert "MIND_API_BIND=0.0.0.0:18600" in content
    assert "MIND_DOCS_BIND=0.0.0.0:18601" in content
    assert "MIND_DEV_MODE=false" in content
    assert "MIND_PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple" in content
    assert "MIND_PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn" in content


def test_scripts_exist_and_executable() -> None:
    """Shell scripts must exist and be executable."""
    for script_name in ("dev.sh", "deploy.sh", "docs-release.sh"):
        script_path = ROOT / "scripts" / script_name
        assert script_path.exists(), f"{script_name} does not exist"
        assert os.access(script_path, os.X_OK), f"{script_name} is not executable"


def test_scripts_use_isolated_env_files_and_projects() -> None:
    dev_script = (ROOT / "scripts" / "dev.sh").read_text(encoding="utf-8")
    deploy_script = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")

    assert 'PROJECT_NAME="mind-dev"' in dev_script
    assert 'LOCAL_ENV_FILE=".env.dev.local"' in dev_script
    assert "--attach" in dev_script
    assert "compose up --build -d" in dev_script
    assert "API 文档" in dev_script
    assert "api_docs_url" in dev_script
    assert 'PROJECT_NAME="mind-prod"' in deploy_script
    assert 'LOCAL_ENV_FILE=".env.prod.local"' in deploy_script
    assert 'MIND_POSTGRES_PASSWORD' in deploy_script
    assert 'DOCS_FILE="compose.docs.yaml"' in deploy_script
    assert "build_docs_site" in deploy_script
    assert "--attach" in deploy_script
    assert "compose up --build -d" in deploy_script
    assert "API 文档" in deploy_script
    assert "api_docs_url" in deploy_script


def test_docs_release_script_builds_and_publishes_static_site() -> None:
    docs_release_script = (ROOT / "scripts" / "docs-release.sh").read_text(encoding="utf-8")

    assert 'PROJECT_NAME="mind-docs"' in docs_release_script
    assert 'COMPOSE_FILE="compose.docs.yaml"' in docs_release_script
    assert 'DOCS_BIND="${DOCS_BIND:-0.0.0.0:18604}"' in docs_release_script
    assert "mkdocs build --strict" in docs_release_script
    assert "publish-local" in docs_release_script


def test_api_dockerfile_bundles_frontend_assets() -> None:
    dockerfile_api = (ROOT / "Dockerfile.api").read_text(encoding="utf-8")

    assert "COPY frontend /app/frontend" in dockerfile_api


def test_python_dockerfiles_enable_cached_dependency_installs() -> None:
    dockerfile_api = (ROOT / "Dockerfile.api").read_text(encoding="utf-8")
    dockerfile_worker = (ROOT / "Dockerfile.worker").read_text(encoding="utf-8")
    dockerfile_docs_dev = (ROOT / "Dockerfile.docs.dev").read_text(encoding="utf-8")

    for dockerfile in (dockerfile_api, dockerfile_worker, dockerfile_docs_dev):
        assert "# syntax=docker/dockerfile:1.7" in dockerfile
        assert "--mount=type=cache,target=/root/.cache/pip" in dockerfile
        assert "pip install --no-build-isolation --no-deps ." in dockerfile

    assert 'COPY pyproject.toml /app/' in dockerfile_api
    assert 'COPY pyproject.toml /app/' in dockerfile_worker
    assert 'COPY pyproject.toml /app/' in dockerfile_docs_dev


def test_deployment_smoke_suite_v1() -> None:
    scenarios = build_deployment_smoke_suite_v1()
    report = evaluate_deployment_smoke_suite(ROOT)

    assert len(scenarios) >= 20
    assert len(report.results) == len(scenarios)
    assert report.pass_rate >= 0.95
    assert all(result.passed for result in report.results)
