"""Documentation system regression tests."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parent.parent

_REQUIRED_DOC_PATHS = (
    "docs/index.md",
    "docs/docs-authoring.md",
    "docs/history-and-evidence.md",
    "docs/product/overview.md",
    "docs/product/quickstart.md",
    "docs/product/deployment.md",
    "docs/product/cli.md",
    "docs/product/api.md",
    "docs/product/mcp.md",
    "docs/product/sessions-and-users.md",
    "docs/reference/cli-reference.md",
    "docs/reference/api-reference.md",
    "docs/reference/mcp-tool-reference.md",
    "docs/reference/config-reference.md",
    "docs/reference/error-reference.md",
    "docs/ops/runbook-deploy.md",
    "docs/ops/runbook-upgrade.md",
    "docs/ops/runbook-troubleshooting.md",
    "docs/ops/security.md",
    "docs/architecture/system-overview.md",
    "docs/architecture/app-layer.md",
    "docs/architecture/storage-model.md",
    "docs/architecture/transport-model.md",
    "docs/architecture/documentation-system.md",
)


def test_pyproject_declares_docs_toolchain_extra() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    optional_dependencies = data["project"]["optional-dependencies"]
    docs_extra = optional_dependencies["docs"]

    assert any(dep.startswith("mkdocs>=") for dep in docs_extra)
    assert any(dep.startswith("mkdocs-material>=") for dep in docs_extra)
    assert any(dep.startswith("mkdocstrings[python]>=") for dep in docs_extra)
    assert any(dep.startswith("mike>=") for dep in docs_extra)


def test_mkdocs_config_exposes_product_grade_nav() -> None:
    config = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))

    assert config["site_name"] == "MIND"
    assert config["theme"]["name"] == "material"
    plugin_names = {
        item if isinstance(item, str) else next(iter(item))
        for item in config["plugins"]
    }
    assert {"search", "mkdocstrings"}.issubset(plugin_names)

    top_level_sections = [next(iter(item)) for item in config["nav"] if isinstance(item, dict)]
    assert top_level_sections == [
        "首页",
        "产品",
        "参考",
        "运维",
        "架构",
        "历史与证据",
    ]

    for doc_path in _collect_nav_paths(config["nav"]):
        assert (ROOT / "docs" / doc_path).exists(), f"mkdocs nav path missing: {doc_path}"


def test_required_product_docs_exist() -> None:
    for relpath in _REQUIRED_DOC_PATHS:
        assert (ROOT / relpath).exists(), f"missing docs page: {relpath}"


def test_docs_entrypoints_describe_preview_and_audiences() -> None:
    docs_index = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    docs_authoring = (ROOT / "docs" / "docs-authoring.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "uv run mkdocs serve" in docs_authoring
    assert "product/" in docs_authoring
    assert "reference/" in docs_authoring
    assert "ops/" in docs_authoring
    assert "architecture/" in docs_authoring

    for entrypoint in ("mind", "mind-api", "mind-mcp", "mindtest"):
        assert entrypoint in docs_index

    assert "./docs/index.md" in readme
    assert "uv run mkdocs serve" in readme


def _collect_nav_paths(nav: list[Any]) -> list[str]:
    paths: list[str] = []
    for item in nav:
        if isinstance(item, dict):
            value = next(iter(item.values()))
            if isinstance(value, str):
                paths.append(value)
            elif isinstance(value, list):
                paths.extend(_collect_nav_paths(value))
        elif isinstance(item, str):
            paths.append(item)
    return paths
