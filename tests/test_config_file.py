"""Tests for mind.toml config file loading and resolution integration."""

from __future__ import annotations

import textwrap
from pathlib import Path

from mind.capabilities.config import resolve_capability_provider_config
from mind.capabilities.config_file import (
    get_evaluation_config,
    get_provider_config,
    load_mind_toml,
)


def test_load_mind_toml_finds_repo_root(tmp_path: Path) -> None:
    """``load_mind_toml`` locates mind.toml via pyproject.toml marker."""

    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")
    config_path = tmp_path / "mind.toml"
    config_path.write_text(
        textwrap.dedent("""\
            [provider]
            provider = "openai"
            model = "gpt-4o"
        """),
    )
    result = load_mind_toml(search_from=tmp_path)
    assert result["provider"]["provider"] == "openai"
    assert result["provider"]["model"] == "gpt-4o"


def test_load_mind_toml_from_subdirectory(tmp_path: Path) -> None:
    """Config is found even when search starts from a subdirectory."""

    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "mind.toml").write_text("[provider]\nprovider = 'claude'\n")
    sub = tmp_path / "mind" / "capabilities"
    sub.mkdir(parents=True)
    result = load_mind_toml(search_from=sub)
    assert result["provider"]["provider"] == "claude"


def test_load_mind_toml_returns_empty_when_missing(tmp_path: Path) -> None:
    """Returns empty dict when mind.toml does not exist."""

    (tmp_path / "pyproject.toml").write_text("")
    result = load_mind_toml(search_from=tmp_path)
    assert result == {}


def test_load_mind_toml_returns_empty_on_invalid_toml(tmp_path: Path) -> None:
    """Returns empty dict when mind.toml has invalid syntax."""

    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "mind.toml").write_text("not valid [[[ toml content")
    result = load_mind_toml(search_from=tmp_path)
    assert result == {}


def test_get_provider_config_extracts_section() -> None:
    toml = {"provider": {"provider": "gemini", "model": "gemini-pro"}}
    cfg = get_provider_config(toml)
    assert cfg == {"provider": "gemini", "model": "gemini-pro"}


def test_get_provider_config_returns_empty_for_missing_section() -> None:
    assert get_provider_config({}) == {}
    assert get_provider_config({"evaluation": {}}) == {}


def test_get_evaluation_config_extracts_section() -> None:
    toml = {"evaluation": {"dataset": "scifact", "strategy": "fixed"}}
    cfg = get_evaluation_config(toml)
    assert cfg == {"dataset": "scifact", "strategy": "fixed"}


def test_resolve_env_overrides_config_file() -> None:
    """Env vars take priority over config file but not over CLI selection."""

    config_file = {"provider": "openai", "model": "gpt-4o", "endpoint": "https://proxy.example.com/v1"}
    env = {"MIND_PROVIDER": "claude", "MIND_MODEL": "from-env"}

    result = resolve_capability_provider_config(
        config_file=config_file,
        env=env,
    )
    # env wins over config_file for provider and model
    assert result.provider == "claude"
    assert result.model == "from-env"
    # endpoint not in env, so config_file applies
    assert result.endpoint == "https://proxy.example.com/v1"


def test_resolve_cli_overrides_config_file() -> None:
    """CLI selection values override config file values."""

    config_file = {"provider": "openai", "model": "gpt-4o"}
    selection = {"provider": "claude", "model": "claude-3-7-sonnet"}

    result = resolve_capability_provider_config(
        selection=selection,
        config_file=config_file,
        env={},
    )
    assert result.provider == "claude"
    assert result.model == "claude-3-7-sonnet"


def test_resolve_env_overrides_config_file_model() -> None:
    """Env vars override config file values."""

    config_file = {"model": "gpt-4o"}
    env = {"MIND_PROVIDER": "openai", "MIND_MODEL": "gpt-4.1-mini"}

    result = resolve_capability_provider_config(
        config_file=config_file,
        env=env,
    )
    assert result.provider == "openai"  # from env
    assert result.model == "gpt-4.1-mini"  # env overrides config_file


def test_resolve_falls_through_to_defaults() -> None:
    """Empty config file means env and defaults still work."""

    result = resolve_capability_provider_config(
        config_file={},
        env={},
    )
    assert result.provider == "stub"
    assert result.model == "deterministic"


def test_resolve_config_file_timeout_ms() -> None:
    """Config file can set timeout_ms."""

    config_file = {"provider": "openai", "timeout_ms": 60000}
    result = resolve_capability_provider_config(
        config_file=config_file,
        env={},
    )
    assert result.timeout_ms == 60000


def test_resolve_config_file_api_version() -> None:
    """Config file can set api_version."""

    config_file = {"provider": "openai", "api_version": "2024-02-01"}
    result = resolve_capability_provider_config(
        config_file=config_file,
        env={},
    )
    assert result.api_version == "2024-02-01"


def test_resolve_config_file_api_key_used_when_no_env() -> None:
    """api_key from config file is used when no env vars are set."""

    config_file = {"provider": "openai", "api_key": "sk-from-toml"}
    result = resolve_capability_provider_config(
        config_file=config_file,
        env={},
    )
    assert result.auth.secret_value == "sk-from-toml"
    assert result.auth.secret_env == "mind.toml"


def test_resolve_env_api_key_overrides_config_file() -> None:
    """Env api_key takes priority over config file api_key."""

    config_file = {"provider": "claude", "api_key": "sk-toml-key"}
    env = {"ANTHROPIC_API_KEY": "sk-env-key"}
    result = resolve_capability_provider_config(
        config_file=config_file,
        env=env,
    )
    assert result.auth.secret_value == "sk-env-key"
    assert result.auth.secret_env == "ANTHROPIC_API_KEY"


def test_resolve_config_file_empty_api_key_falls_through() -> None:
    """Empty api_key string is ignored; env vars are used instead."""

    config_file = {"provider": "openai", "api_key": ""}
    env = {"OPENAI_API_KEY": "sk-env-key"}
    result = resolve_capability_provider_config(
        config_file=config_file,
        env=env,
    )
    assert result.auth.secret_value == "sk-env-key"
    assert result.auth.secret_env == "OPENAI_API_KEY"
