"""WP-5 deployment asset verification tests."""

from __future__ import annotations

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
    for dockerfile_name in ("Dockerfile.api", "Dockerfile.worker"):
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
    assert compose_data["services"]["api"]["build"]["dockerfile"] == "Dockerfile.api"
    assert compose_data["services"]["worker"]["build"]["dockerfile"] == "Dockerfile.worker"
    assert (
        compose_data["services"]["api"]["depends_on"]["postgres"]["condition"]
        == "service_healthy"
    )
    assert (
        compose_data["services"]["worker"]["depends_on"]["postgres"]["condition"]
        == "service_healthy"
    )


def test_env_example_covers_required_vars() -> None:
    env_path = ROOT / ".env.example"
    content = env_path.read_text(encoding="utf-8")

    for env_var in (
        "MIND_POSTGRES_DSN",
        "MIND_API_KEY",
        "MIND_PROVIDER",
        "MIND_MODEL",
        "MIND_LOG_LEVEL",
        "MIND_DEV_MODE",
    ):
        assert f"{env_var}=" in content


def test_deployment_smoke_suite_v1() -> None:
    scenarios = build_deployment_smoke_suite_v1()
    report = evaluate_deployment_smoke_suite(ROOT)

    assert len(scenarios) >= 20
    assert len(report.results) == len(scenarios)
    assert report.pass_rate >= 0.95
    assert all(result.passed for result in report.results)
