from __future__ import annotations

from pathlib import Path

import pytest

from mind.frontend import (
    FrontendSettingsUpdateRequest,
    build_frontend_settings_mutation_result,
    build_frontend_settings_page,
    build_frontend_settings_snapshot,
    dump_frontend_settings_snapshot_state,
    load_frontend_settings_snapshot_state,
    preview_frontend_settings_update,
)
from mind.kernel.store import SQLiteMemoryStore


def test_frontend_settings_update_requires_at_least_one_change() -> None:
    with pytest.raises(ValueError, match="at least one change"):
        FrontendSettingsUpdateRequest()


def test_frontend_settings_page_projects_manual_payloads() -> None:
    page = build_frontend_settings_page(
        {
            "backend": "postgresql",
            "profile": "postgres_main",
            "backend_source": "profile:postgres_main",
            "profile_source": "env:MIND_CLI_PROFILE",
            "dev_mode": True,
            "dev_telemetry_configured": True,
        },
        {
            "provider": "claude",
            "provider_family": "claude",
            "model": "claude-3-7-sonnet",
            "endpoint": "https://api.anthropic.com/v1/messages",
            "status": "available",
            "execution": "claude_messages_adapter_ready",
            "auth": {"configured": True},
            "supported_capabilities": [
                "summarize",
                "reflect",
                "answer",
                "offline_reconstruct",
            ],
        },
    )

    assert page.runtime.backend == "postgresql"
    assert page.runtime.debug_available is True
    assert page.provider.provider_family == "claude"
    assert "dev_mode" in page.options.editable_keys
    assert "postgres_main" in page.options.profiles


def test_frontend_settings_page_projects_real_system_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mind.app.services.system import SystemStatusService
    from mind.cli_config import resolve_cli_config

    monkeypatch.setenv("MIND_DEV_MODE", "true")
    monkeypatch.setenv("MIND_DEV_TELEMETRY_PATH", str(tmp_path / "telemetry.jsonl"))
    monkeypatch.setenv("MIND_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")

    store = SQLiteMemoryStore(str(tmp_path / "frontend_settings.sqlite3"))
    config = resolve_cli_config(
        profile="postgres_main",
        postgres_dsn="postgresql+psycopg://user:secret@localhost:5432/mind",
    )
    service = SystemStatusService(store, config=config)

    config_resp = service.config_summary()
    provider_resp = service.provider_status()

    assert config_resp.result is not None
    assert provider_resp.result is not None

    page = build_frontend_settings_page(config_resp.result, provider_resp.result)

    assert page.runtime.profile == "postgres_main"
    assert page.runtime.dev_mode is True
    assert page.runtime.dev_telemetry_configured is True
    assert page.provider.provider == "openai"
    assert page.provider.auth_configured is True
    assert page.provider.execution == "openai_responses_adapter_ready"


def test_frontend_settings_preview_projects_effective_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mind.cli_config import resolve_cli_config

    monkeypatch.setenv("MIND_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")

    config = resolve_cli_config(
        profile="postgres_main",
        postgres_dsn="postgresql+psycopg://user:secret@localhost:5432/mind",
    )
    preview = preview_frontend_settings_update(
        {
            "provider": "claude",
            "model": "claude-3-7-sonnet",
            "dev_mode": True,
            "backend": "sqlite",
        },
        current_config=config,
        env={
            "MIND_PROVIDER": "openai",
            "OPENAI_API_KEY": "test-secret",
            "MIND_DEV_TELEMETRY_PATH": str(tmp_path / "telemetry.jsonl"),
        },
    )

    assert preview.backend_override == "sqlite"
    assert preview.preview.runtime.backend == "sqlite"
    assert preview.preview.provider.provider == "claude"
    assert preview.preview.runtime.dev_mode is True
    assert set(preview.changed_keys) >= {"backend", "provider", "model", "dev_mode"}
    assert preview.applied_env_overrides["MIND_PROVIDER"] == "claude"


def test_frontend_settings_snapshot_state_round_trip() -> None:
    from mind.cli_config import resolve_cli_config

    preview = preview_frontend_settings_update(
        {"provider": "openai", "model": "gpt-4.1-mini"},
        current_config=resolve_cli_config(
            profile="postgres_main",
            postgres_dsn="postgresql+psycopg://user:secret@localhost:5432/mind",
        ),
        env={},
    )
    snapshot = build_frontend_settings_snapshot(
        preview,
        snapshot_id="snap-001",
        action="apply",
    )
    dumped = dump_frontend_settings_snapshot_state(
        {"current_snapshot": snapshot, "previous_snapshot": None}
    )
    restored = load_frontend_settings_snapshot_state(dumped)

    assert restored.current_snapshot is not None
    assert restored.current_snapshot.snapshot_id == "snap-001"
    assert restored.restore_available is False


def test_frontend_settings_mutation_result_reports_restore_state() -> None:
    from mind.cli_config import resolve_cli_config

    preview = preview_frontend_settings_update(
        {"profile": "postgres_main", "dev_mode": True},
        current_config=resolve_cli_config(
            profile="postgres_main",
            postgres_dsn="postgresql+psycopg://user:secret@localhost:5432/mind",
        ),
        env={},
    )
    current_snapshot = build_frontend_settings_snapshot(
        preview,
        snapshot_id="snap-current",
        action="apply",
    )
    previous_snapshot = build_frontend_settings_snapshot(
        preview,
        snapshot_id="snap-previous",
        action="apply",
    )
    result = build_frontend_settings_mutation_result(
        action="restore",
        current_snapshot=current_snapshot,
        previous_snapshot=previous_snapshot,
        preview=preview,
    )

    assert result.action == "restore"
    assert result.restore_available is True
    assert result.current_snapshot.snapshot_id == "snap-current"
    assert result.previous_snapshot is not None
