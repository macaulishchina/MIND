"""Phase M static frontend mount tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from mind.api.app import create_app
from mind.cli_config import resolve_cli_config


@pytest.fixture
async def static_frontend_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("MIND_API_KEY", "test-api-key")
    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "phase_m_frontend_static.sqlite3"),
        allow_sqlite=True,
    )
    app = create_app(config)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=True,
        ) as client:
            yield client


@pytest.mark.anyio
async def test_static_frontend_index_is_mounted(
    static_frontend_client: httpx.AsyncClient,
) -> None:
    response = await static_frontend_client.get("/frontend/")

    assert response.status_code == 200
    assert "MIND 记忆控制台" in response.text
    assert "./app.js" in response.text
    assert "./styles.css" in response.text
    assert 'id="gate-demo-panel"' in response.text
    assert 'id="ingest-form"' in response.text
    assert 'id="retrieve-form"' in response.text
    assert 'id="access-form"' in response.text
    assert 'id="offline-form"' in response.text
    assert 'id="settings-form"' in response.text
    assert 'id="settings-apply"' in response.text
    assert 'id="settings-restore"' in response.text


@pytest.mark.anyio
async def test_static_frontend_assets_are_served(
    static_frontend_client: httpx.AsyncClient,
) -> None:
    app_js = await static_frontend_client.get("/frontend/app.js")
    styles = await static_frontend_client.get("/frontend/styles.css")

    assert app_js.status_code == 200
    assert "loadCatalog" in app_js.text
    assert "loadGateDemo" in app_js.text
    assert "previewSettings" in app_js.text
    assert "applySettings" in app_js.text
    assert "restoreSettings" in app_js.text
    assert "submitIngest" in app_js.text
    assert "选择依据" in app_js.text
    assert "参考依据" in app_js.text
    assert "submitRetrieve" in app_js.text
    assert "submitAccess" in app_js.text
    assert "submitOffline" in app_js.text
    assert "status-chip" in app_js.text
    assert styles.status_code == 200
    assert ".workbench" in styles.text
    assert ".auth-panel" in styles.text
    assert ".wide-field" in styles.text
    assert ".overview-card" in styles.text
