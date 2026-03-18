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
    favicon = await static_frontend_client.get("/favicon.ico")

    assert response.status_code == 200
    assert favicon.status_code == 200
    assert "MIND 记忆控制台" in response.text
    assert "./app.js" in response.text
    assert "./styles/tokens.css" in response.text
    assert "./styles/layout.css" in response.text
    assert "./styles/components.css" in response.text
    assert "./styles/workspaces.css" in response.text
    assert "./styles/modals.css" in response.text
    assert 'id="gate-demo-panel"' in response.text
    assert 'id="ingest-form"' in response.text
    assert 'id="retrieve-form"' in response.text
    assert 'id="access-form"' in response.text
    assert 'id="offline-form"' in response.text
    assert 'id="benchmark-form"' in response.text
    assert 'id="ops-chain-shell"' in response.text
    assert 'id="ops-chain-backdrop"' in response.text
    assert 'id="ops-chain-head"' in response.text
    assert 'id="ops-chain-body"' in response.text
    assert 'id="ops-chain-close"' in response.text
    assert 'id="ops-chain-restore"' in response.text
    assert 'data-open-chain="module-ingest"' in response.text
    assert 'data-open-chain="module-retrieve"' in response.text
    assert 'data-open-chain="module-access"' in response.text
    assert 'data-open-chain="module-offline"' in response.text
    assert 'data-open-chain="module-benchmark"' in response.text
    assert 'id="workspace-settings"' in response.text
    assert 'id="settings-form"' in response.text
    assert 'id="settings-tab-general"' in response.text
    assert 'id="settings-tab-llm"' in response.text
    assert 'id="settings-panel-llm"' in response.text
    assert 'id="llm-protocol-grid"' in response.text
    assert 'id="llm-service-form"' in response.text
    assert 'id="llm-service-list"' in response.text
    assert 'id="llm-service-save"' in response.text
    assert 'id="llm-service-icon-file"' in response.text
    assert 'id="llm-icon-preview"' in response.text
    assert 'id="llm-icon-upload"' in response.text
    assert 'id="llm-trace-modal"' in response.text
    assert 'id="llm-trace-body"' in response.text
    assert "data-llm-trace-modal-close" in response.text


@pytest.mark.anyio
async def test_static_frontend_assets_are_served(
    static_frontend_client: httpx.AsyncClient,
) -> None:
    app_js = await static_frontend_client.get("/frontend/app.js")
    api_js = await static_frontend_client.get("/frontend/api.js")
    constants_js = await static_frontend_client.get("/frontend/app/constants.js")
    core_constants_js = await static_frontend_client.get("/frontend/app/core/constants.js")
    utils_js = await static_frontend_client.get("/frontend/app/utils.js")
    operation_chain_js = await static_frontend_client.get("/frontend/app/operation-chain.js")
    feature_overview_js = await static_frontend_client.get("/frontend/app/features/overview.js")
    feature_operation_chain_js = await static_frontend_client.get(
        "/frontend/app/features/operation-chain.js"
    )
    feature_settings_general_js = await static_frontend_client.get(
        "/frontend/app/features/settings-general.js"
    )
    feature_settings_llm_js = await static_frontend_client.get(
        "/frontend/app/features/settings-llm.js"
    )
    core_dom_js = await static_frontend_client.get("/frontend/app/core/dom.js")
    core_store_js = await static_frontend_client.get("/frontend/app/core/store.js")
    core_router_js = await static_frontend_client.get("/frontend/app/core/router.js")
    core_ui_context_js = await static_frontend_client.get("/frontend/app/core/ui-context.js")
    core_actions_js = await static_frontend_client.get("/frontend/app/core/actions.js")
    core_api_client_js = await static_frontend_client.get("/frontend/app/core/api-client.js")
    workbench_state_js = await static_frontend_client.get("/frontend/app/workbench-state.js")
    workbench_navigation_js = await static_frontend_client.get(
        "/frontend/app/workbench-navigation.js"
    )
    tokens_css = await static_frontend_client.get("/frontend/styles/tokens.css")
    layout_css = await static_frontend_client.get("/frontend/styles/layout.css")
    components_css = await static_frontend_client.get("/frontend/styles/components.css")
    workspaces_css = await static_frontend_client.get("/frontend/styles/workspaces.css")
    modals_css = await static_frontend_client.get("/frontend/styles/modals.css")
    favicon_svg = await static_frontend_client.get("/frontend/favicon.svg")

    assert app_js.status_code == 200
    assert api_js.status_code == 200
    assert constants_js.status_code == 200
    assert core_constants_js.status_code == 200
    assert utils_js.status_code == 200
    assert operation_chain_js.status_code == 200
    assert feature_overview_js.status_code == 200
    assert feature_operation_chain_js.status_code == 200
    assert feature_settings_general_js.status_code == 200
    assert feature_settings_llm_js.status_code == 200
    assert core_dom_js.status_code == 200
    assert core_store_js.status_code == 200
    assert core_router_js.status_code == 200
    assert core_ui_context_js.status_code == 200
    assert core_actions_js.status_code == 200
    assert core_api_client_js.status_code == 200
    assert workbench_state_js.status_code == 200
    assert workbench_navigation_js.status_code == 200
    assert "loadCatalog" in app_js.text
    assert "loadGateDemo" in app_js.text
    assert "applySettings" in app_js.text
    assert "workspace-settings" in app_js.text
    assert "settings-panel-llm" in app_js.text
    assert "./app/core/actions.js" in app_js.text
    assert "./app/core/api-client.js" in app_js.text
    assert "./app/core/dom.js" in app_js.text
    assert "./app/core/router.js" in app_js.text
    assert "./app/core/store.js" in app_js.text
    assert "./app/core/ui-context.js" in app_js.text
    assert "./app/core/constants.js" in app_js.text
    assert "./app/features/overview.js" in app_js.text
    assert "./app/features/operation-chain.js" in app_js.text
    assert "./app/features/settings-general.js" in app_js.text
    assert "./app/features/settings-llm.js" in app_js.text
    assert "./app/utils.js" in app_js.text
    assert "submitIngest" in app_js.text
    assert "submitRetrieve" in app_js.text
    assert "submitAccess" in app_js.text
    assert "submitOffline" in app_js.text
    assert "runMemoryLifecycleBenchmark" in app_js.text
    assert "loadMemoryLifecycleBenchmarkReport" in app_js.text
    assert "回答详情" in app_js.text
    assert "syncAuthSubmitLabel" in app_js.text
    assert "GATE_KIND_LABELS" in constants_js.text
    assert 'export * from "../constants.js"' in core_constants_js.text
    assert "OPERATION_CHAIN_CONFIG" in constants_js.text
    assert "LLM_PROTOCOL_LIBRARY" in constants_js.text
    assert "compressLlmServiceIconFile" in utils_js.text
    assert "renderLlmServiceAvatar" in utils_js.text
    assert "localizeAccessDepth" in utils_js.text
    assert "formatValue" in utils_js.text
    assert "createOperationChainManager" in operation_chain_js.text
    assert "buildRunningOperationChain" in operation_chain_js.text
    assert "buildSuccessfulOperationChain" in operation_chain_js.text
    assert "renderOperationChain" in operation_chain_js.text
    assert "createOverviewFeature" in feature_overview_js.text
    assert "renderOverview" in feature_overview_js.text
    assert "createSettingsGeneralFeature" in feature_settings_general_js.text
    assert "renderSettingsPage" in feature_settings_general_js.text
    assert "createSettingsLlmFeature" in feature_settings_llm_js.text
    assert "collectLlmServicePayload" in feature_settings_llm_js.text
    assert "updateDraftIconFromFile" in feature_settings_llm_js.text
    assert (
        'export { createOperationChainManager } from "../operation-chain.js";'
        in feature_operation_chain_js.text
    )
    assert "ops-chain-shell" in core_dom_js.text
    assert "未调用 LLM，走内建路径" in operation_chain_js.text
    assert "查看本轮提交、发送给 AI 的原文，以及 AI 的原始返回" in operation_chain_js.text
    assert "AI 原始返回" in operation_chain_js.text
    assert "查看本轮完整请求与回答" in operation_chain_js.text
    assert "authForm" in core_dom_js.text
    assert "llmProtocolGrid" in core_dom_js.text
    assert "createStore" in core_store_js.text
    assert "createWorkbenchRouter" in core_router_js.text
    assert "parseWorkbenchHash" in core_ui_context_js.text
    assert "resolveInitialWorkbenchContext" in core_ui_context_js.text
    assert "createUiActionRunner" in core_actions_js.text
    assert "../../api.js" in core_api_client_js.text
    assert '"/v1/frontend/access"' in api_js.text
    assert '"/v1/frontend/benchmark:run"' in api_js.text
    assert '"/v1/frontend/benchmark:report"' in api_js.text
    assert "loadWorkbenchContext" in workbench_state_js.text
    assert "resolveInitialWorkbenchContext" in workbench_state_js.text
    assert "createWorkbenchRouter" in workbench_navigation_js.text
    assert tokens_css.status_code == 200
    assert layout_css.status_code == 200
    assert components_css.status_code == 200
    assert workspaces_css.status_code == 200
    assert modals_css.status_code == 200
    assert favicon_svg.status_code == 200
    assert ":root" in tokens_css.text
    assert ".sidebar" in layout_css.text
    assert ".content" in layout_css.text
    assert ".overview-grid" in workspaces_css.text
    assert ".ops-chain-shell" in workspaces_css.text
    assert ".ops-chain-step" in workspaces_css.text
    assert ".ops-chain-backdrop" in workspaces_css.text
    assert ".ops-chain-restore" in workspaces_css.text
    assert ".llm-protocol-grid" in workspaces_css.text
    assert ".llm-service-list" in workspaces_css.text
    assert ".llm-icon-editor" in workspaces_css.text
    assert ".llm-icon-preview" in workspaces_css.text
    assert ".form-grid" in components_css.text
    assert ".metric-list" in components_css.text
    assert ".modal-shell" in modals_css.text
    assert ".llm-trace-modal-card" in modals_css.text
    assert ".llm-trace-exchange" in modals_css.text
