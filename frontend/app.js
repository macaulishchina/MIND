import {
  activateLlmService,
  applySettings,
  deleteLlmService,
  discoverLlmModels,
  loadCatalog,
  loadDebugTimeline,
  loadGateDemo,
  loadSettings,
  submitAccess,
  submitIngest,
  submitOffline,
  submitRetrieve,
  upsertLlmService,
} from "./app/core/api-client.js";
import {
  DEFAULTS,
  GATE_KIND_LABELS,
  INGEST_HISTORY_KEY,
  INGEST_PAGE_SIZE,
  LLM_PROTOCOL_LIBRARY,
  MIN_BUSY_MS,
  STORAGE_KEY,
} from "./app/core/constants.js";
import { createUiActionRunner } from "./app/core/actions.js";
import { elements } from "./app/core/dom.js";
import { createWorkbenchRouter } from "./app/core/router.js";
import { createStore } from "./app/core/store.js";
import { resolveInitialWorkbenchContext } from "./app/core/ui-context.js";
import { createOverviewFeature } from "./app/features/overview.js";
import { createOperationChainManager } from "./app/features/operation-chain.js";
import { createSettingsGeneralFeature } from "./app/features/settings-general.js";
import { createSettingsLlmFeature } from "./app/features/settings-llm.js";
import {
  buildLlmAvatar,
  clamp,
  compressLlmServiceIconFile,
  delay,
  escapeHtml,
  formatDateTime,
  formatValue,
  getAnswerModeFromSettings,
  isPositiveInteger,
  localizeAccessDepth,
  localizeAnswerMode,
  localizeAuthMode,
  localizeContentType,
  localizeEntrypoint,
  localizeGateEntry,
  localizeOfflineJobKind,
  localizeProviderExecution,
  localizeProviderFamily,
  localizeProviderStatus,
  localizeRetryPolicy,
  localizeSettingKey,
  normalizeLlmIconValue,
  renderLlmServiceAvatar,
  renderMetricList,
  truncateText,
} from "./app/utils.js";

const initialWorkbenchContext = resolveInitialWorkbenchContext(
  window.location.hash,
  window.localStorage,
  {
    workspaceIds: elements.workspacePanels.map((panel) => panel.id),
    operationIds: elements.operationPanels.map((panel) => panel.id),
    settingsSectionIds: elements.settingsPanels.map((panel) => panel.id),
  },
  DEFAULTS,
);

const store = createStore({
  apiKey: window.localStorage.getItem(STORAGE_KEY) || "",
  catalogPage: null,
  gateDemoPage: null,
  settingsPage: null,
  llmEditorDraft: null,
  llmServiceModelSelections: {},
  llmNotice: null,
  llmModalOpen: false,
  llmTraceModalOpen: false,
  llmTraceModalPayload: null,
  ingestSubmissionHistory: loadStoredIngestHistory(),
  ingestHistoryPage: 1,
  ingestHistoryCursor: -1,
  ingestDraftSnapshot: "",
  busyActions: new Set(),
  operationChainSnapshots: {
    "module-ingest": null,
    "module-retrieve": null,
    "module-access": null,
    "module-offline": null,
  },
  operationChainDrawerOpen: false,
  operationChainHidden: false,
  activeWorkspace: initialWorkbenchContext.activeWorkspace,
  activeOperation: initialWorkbenchContext.activeOperation,
  activeSettingsSection: initialWorkbenchContext.activeSettingsSection,
});
const state = store.getState();
let llmFeature;

const operationChain = createOperationChainManager({
  elements,
  state,
  defaults: DEFAULTS,
  getAnswerModeFromSettings,
  getLlmActiveService: (...args) => llmFeature.getLlmActiveService(...args),
  syncModalOpenState,
});

const {
  buildErrorOperationChain,
  buildRunningOperationChain,
  buildSuccessfulOperationChain,
  closeLlmTraceModal,
  focusOperationChainShell,
  handleBodyClick: handleOperationChainBodyClick,
  handleEscape: handleOperationChainEscape,
  handleOpenButton: handleOperationChainOpenButton,
  renderOperationChain,
  reset: resetOperationChain,
  setOperationChainDrawerOpen,
  setOperationChainHidden,
  setOperationChainSnapshot,
  syncOperationChainVisibility,
} = operationChain;

const workbenchRouter = createWorkbenchRouter({
  windowRef: window,
  storage: window.localStorage,
  elements,
  state,
  defaults: DEFAULTS,
  renderOperationChain,
  setOperationChainDrawerOpen,
});

const {
  navigate,
  setActiveWorkspace,
  setActiveOperation,
  setActiveSettingsSection,
} = workbenchRouter;

function setStatus(message) {
  elements.authStatus.textContent = message;
}

function syncModalOpenState() {
  document.body.classList.toggle(
    "modal-open",
    Boolean(state.llmModalOpen || state.llmTraceModalOpen),
  );
}

const overviewFeature = createOverviewFeature({
  documentRef: document,
  elements,
  navigate,
  state,
  getAnswerModeFromSettings,
  getLlmActiveService: (...args) => llmFeature.getLlmActiveService(...args),
  localizeAnswerMode,
  localizeEntrypoint,
  localizeProviderFamily,
  localizeGateEntry,
  GATE_KIND_LABELS,
  escapeHtml,
});

const settingsGeneralFeature = createSettingsGeneralFeature({
  elements,
  getAnswerModeFromSettings,
  getLlmActiveService: (...args) => llmFeature.getLlmActiveService(...args),
  localizeAnswerMode,
  localizeProviderFamily,
  localizeSettingKey,
  formatValue,
  renderMetricList,
  escapeHtml,
});

llmFeature = createSettingsLlmFeature({
  windowRef: window,
  state,
  elements,
  llmProtocolLibrary: LLM_PROTOCOL_LIBRARY,
  syncModalOpenState,
  syncActionAvailability,
  getAnswerModeFromSettings,
  localizeAnswerMode,
  localizeProviderFamily,
  normalizeLlmIconValue,
  buildLlmAvatar,
  renderLlmServiceAvatar,
  compressLlmServiceIconFile,
  escapeHtml,
  loadSettings,
  upsertLlmService,
  discoverLlmModels,
  activateLlmService,
  deleteLlmService,
  renderSettingsOptions: settingsGeneralFeature.renderSettingsOptions,
  renderSettingsPage: settingsGeneralFeature.renderSettingsPage,
  renderOverview: overviewFeature.renderOverview,
  updateShellSignals,
  syncPanelGuards,
  renderOperationChain,
});

const {
  getUserFacingCatalogEntries,
  jumpToOverviewEntrypoint,
  renderOverviewEmpty,
  renderGateDemoEmpty,
  renderOverview,
  renderGateDemo,
} = overviewFeature;

const {
  renderSettingsOptions,
  renderSettingsPage,
  renderSettingsMutation,
} = settingsGeneralFeature;

const {
  getLlmServiceById,
  getLlmActiveService,
  getLlmSelectedService,
  getSelectedLlmDraft,
  primeLlmEditorFromSettings,
  setLlmModalOpen,
  openLlmEditor,
  closeLlmEditor,
  updateLlmEditorDraft,
  syncLlmEditorDraftUi,
  renderLlmIconPreview,
  buildSelectedLlmApplyRequest,
  confirmDeleteLlmService,
  renderLlmStatus,
  renderLlmPage,
  saveCurrentLlmService,
  discoverModelsForService,
  discoverModelsFromEditor,
  activateSavedLlmService,
  deleteSavedLlmService,
  updateDraftIconFromFile,
} = llmFeature;

function getOfflineTargetRefs() {
  return elements.offlineTargetRefs.value
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

function hasDebugFilters() {
  return Boolean(
    elements.debugRunId.value.trim()
    || elements.debugOperationId.value.trim()
    || elements.debugObjectId.value.trim(),
  );
}

function applyButtonDisabledState(button) {
  if (!button) {
    return;
  }

  const lockedByPanel = Boolean(button.closest(".panel-disabled"));
  const lockedByRule = button.dataset.ruleDisabled === "true";
  const busy = button.dataset.busy === "true";
  button.disabled = lockedByPanel || lockedByRule || busy;
}

function syncAuthSubmitLabel() {
  if (!elements.authSubmit || elements.authSubmit.dataset.busy === "true") {
    return;
  }

  const inputValue = elements.apiKey.value.trim();
  const matchesCurrent = Boolean(state.apiKey && inputValue && inputValue === state.apiKey);
  const label = matchesCurrent
    ? "已连接"
    : (state.apiKey && inputValue ? "重新连接" : "连接工作台");

  elements.authSubmit.textContent = label;
  elements.authSubmit.dataset.defaultLabel = label;
  elements.authSubmit.dataset.connected = matchesCurrent ? "true" : "false";
}

function setButtonRuleDisabled(button, disabled) {
  if (!button) {
    return;
  }
  button.dataset.ruleDisabled = disabled ? "true" : "false";
  applyButtonDisabledState(button);
}

function syncActionAvailability() {
  const authInput = elements.apiKey.value.trim();
  const authMatchesCurrent = Boolean(state.apiKey && authInput && authInput === state.apiKey);
  const offlineNeedsEpisode = elements.offlineJobKind.value === "reflect_episode";
  const offlineSubmitDisabled = offlineNeedsEpisode
    ? !elements.offlineEpisodeId.value.trim()
    : getOfflineTargetRefs().length < 2 || !elements.offlineReason.value.trim();
  const llmDraft = getSelectedLlmDraft();
  const llmCanSave = Boolean(
    state.apiKey
    && llmDraft.protocol
    && llmDraft.name.trim()
    && llmDraft.endpoint.trim(),
  );
  const llmHasSavedKey = Boolean(llmDraft.serviceId && getLlmServiceById(llmDraft.serviceId)?.api_key_saved);
  const llmCanDiscover = Boolean(llmCanSave && (llmDraft.apiKey.trim() || llmHasSavedKey));
  const llmSwitchTarget = getLlmActiveService(state.settingsPage) || getLlmSelectedService(state.settingsPage);
  const canSwitchToLlm = Boolean(llmSwitchTarget?.active_model);

  setButtonRuleDisabled(elements.authSubmit, !authInput || authMatchesCurrent);
  syncAuthSubmitLabel();
  setButtonRuleDisabled(elements.clearKey, !state.apiKey && !elements.apiKey.value.trim());
  setButtonRuleDisabled(
    elements.ingestSubmit,
    !elements.ingestContent.value.trim() || !isPositiveInteger(elements.ingestTimestampOrder.value),
  );
  setButtonRuleDisabled(
    elements.retrieveSubmit,
    !elements.retrieveQuery.value.trim() || !isPositiveInteger(elements.retrieveMaxCandidates.value),
  );
  setButtonRuleDisabled(elements.accessSubmit, !elements.accessQuery.value.trim());
  setButtonRuleDisabled(elements.offlineSubmit, offlineSubmitDisabled);
  setButtonRuleDisabled(
    elements.settingsProvider,
    !state.apiKey || (elements.settingsProvider.value === "llm" && !canSwitchToLlm),
  );
  setButtonRuleDisabled(elements.llmCreateService, !state.apiKey);
  setButtonRuleDisabled(elements.llmServiceSave, !llmCanSave);
  setButtonRuleDisabled(elements.llmServiceDiscover, !llmCanDiscover);
  setButtonRuleDisabled(elements.llmServiceDelete, !state.apiKey || !llmDraft.serviceId);
  setButtonRuleDisabled(elements.llmEditorReset, !state.apiKey);
  setButtonRuleDisabled(elements.debugSubmit, !hasDebugFilters());
}

const uiActions = createUiActionRunner({
  state,
  setStatus,
  syncActionAvailability,
  applyButtonDisabledState,
  delay,
});

const {
  bindClickAction,
  bindFormAction,
  runUiAction,
  setButtonBusy,
} = uiActions;

function loadStoredIngestHistory() {
  try {
    const raw = window.localStorage.getItem(INGEST_HISTORY_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .filter(
        (item) =>
          item
          && typeof item.content === "string"
          && typeof item.object_id === "string"
          && typeof item.episode_id === "string"
          && typeof item.timestamp_order === "number",
      )
      .map((item) => ({
        id: typeof item.id === "string" ? item.id : `${item.object_id}-${item.timestamp_order}`,
        content: item.content,
        object_id: item.object_id,
        episode_id: item.episode_id,
        timestamp_order: item.timestamp_order,
        version: Number.parseInt(String(item.version), 10) || 1,
        provenance_id: item.provenance_id || null,
        trace_ref: item.trace_ref || null,
        submitted_at: item.submitted_at || new Date().toISOString(),
        episode_mode: item.episode_mode === "generated" ? "generated" : "provided",
      }));
  } catch {
    return [];
  }
}

function persistIngestHistory() {
  try {
    window.localStorage.setItem(
      INGEST_HISTORY_KEY,
      JSON.stringify(state.ingestSubmissionHistory),
    );
  } catch {
    setStatus("浏览器本地写入历史已满，本次仅保留当前会话显示。");
  }
}

function getIngestInputHistory() {
  return state.ingestSubmissionHistory.map((item) => item.content);
}

function updateShellSignals() {
  const hasApiKey = Boolean(state.apiKey);
  const catalogEntries = getUserFacingCatalogEntries(state.catalogPage);
  const runtime = state.settingsPage?.runtime || null;
  const devModeEnabled = Boolean(runtime?.dev_mode);
  const answerMode = state.settingsPage ? getAnswerModeFromSettings(state.settingsPage) : null;

  elements.authStatus.textContent = hasApiKey
    ? (
      state.catalogPage || state.settingsPage
        ? "可以继续操作。"
        : "正在同步工作台。"
    )
    : "输入访问口令后即可连接工作台。";
  elements.catalogSummary.textContent = hasApiKey
    ? catalogEntries.length
      ? `功能：${catalogEntries.length} 个入口已就绪`
      : "正在同步功能列表"
    : "功能：未同步";
  elements.runtimeSummary.textContent = runtime
    ? `环境：${runtime.profile} / ${localizeAnswerMode(answerMode)}`
    : "环境：未同步";
  elements.workflowSummary.textContent = !hasApiKey
    ? "工作状态：待连接"
    : devModeEnabled
      ? "工作状态：可排查"
      : "工作状态：可使用";
  syncAuthSubmitLabel();
}

function resetIngestHistoryNavigation() {
  state.ingestHistoryCursor = -1;
  state.ingestDraftSnapshot = "";
}

function syncIngestFieldHints(orderMessage) {
  const historyCount = getIngestInputHistory().length;
  const episodeId = elements.ingestEpisodeId.value.trim();
  const timestampOrder = Number.parseInt(elements.ingestTimestampOrder.value, 10) || 1;

  elements.ingestContentHelp.textContent = historyCount
    ? `光标在开头或结尾时，可用上下键翻看最近写过的内容，当前已记住 ${historyCount} 条。`
    : "光标在开头或结尾时，可用上下键翻看最近写过的内容。";
  elements.ingestEpisodeHelp.textContent = episodeId
    ? `当前会继续写入这个分组；如果想另起一组，可以清空这里或直接重置。`
    : "未填写时，系统会自动新建一个分组，并回填到这里。";
  elements.ingestOrderHelp.textContent =
    orderMessage
    || (
      episodeId
        ? `这是这个分组里的第 ${timestampOrder} 条内容；保存成功后会自动为下一条加 1。`
        : "时间顺序表示同一分组里的先后位置；继续写入时会自动递增。"
    );
  syncActionAvailability();
}

function rememberIngestSubmission(result, request) {
  state.ingestSubmissionHistory.unshift({
    id: `${result.object_id}-${Date.now()}`,
    content: request.content,
    object_id: result.object_id,
    episode_id: result.episode_id,
    timestamp_order: request.timestamp_order,
    version: result.version,
    provenance_id: result.provenance_id || null,
    trace_ref: result.trace_ref || null,
    submitted_at: new Date().toISOString(),
    episode_mode: request.episode_id ? "provided" : "generated",
  });
  state.ingestHistoryPage = 1;
  persistIngestHistory();
}

function renderIngestHistory() {
  const records = state.ingestSubmissionHistory;
  if (!records.length) {
    elements.ingestResult.innerHTML = `
      <div class="empty-state">这里还没有保存记录。每次写入成功后，最近写过的内容都会显示在这里。</div>
    `;
    return;
  }

  const totalPages = Math.max(1, Math.ceil(records.length / INGEST_PAGE_SIZE));
  state.ingestHistoryPage = clamp(state.ingestHistoryPage, 1, totalPages);
  const startIndex = (state.ingestHistoryPage - 1) * INGEST_PAGE_SIZE;
  const visibleRecords = records.slice(startIndex, startIndex + INGEST_PAGE_SIZE);

  elements.ingestResult.innerHTML = `
    <div class="ingest-history-shell">
      <div class="ingest-history-intro">
        <div>
          <div class="status status-ok">最近已保存 ${records.length} 条记录</div>
          <p class="meta">这些记录只保存在当前浏览器里，方便继续填写和回看。</p>
        </div>
      </div>
      <div class="ingest-history-list">
        ${visibleRecords
          .map(
            (record) => `
              <article class="ingest-history-item">
                <div class="history-headline">
                  <div>
                    <strong>${escapeHtml(record.episode_mode === "generated" ? "新分组记录" : "继续写入记录")}</strong>
                    <span class="mini-badge">${escapeHtml(
                      record.episode_mode === "generated" ? "系统新建分组" : "沿用原分组",
                    )}</span>
                  </div>
                  <div class="history-time">${escapeHtml(formatDateTime(record.submitted_at))}</div>
                </div>
                <div class="history-content">${escapeHtml(record.content)}</div>
                <div class="history-meta-grid">
                  <div class="history-meta">
                    <span>记录分组</span>
                    <strong>${escapeHtml(record.episode_id)}</strong>
                  </div>
                  <div class="history-meta">
                    <span>时间顺序</span>
                    <strong>${escapeHtml(record.timestamp_order)}</strong>
                  </div>
                  <div class="history-meta">
                    <span>记录编号</span>
                    <strong>${escapeHtml(record.object_id)}</strong>
                  </div>
                </div>
              </article>
            `,
          )
          .join("")}
      </div>
      <div class="history-footer">
        <p class="meta">每页显示 10 条，最新内容排在最前面。</p>
        <div class="history-pager">
          <button class="btn btn-ghost pager-btn" type="button" data-ingest-page="prev" ${
            state.ingestHistoryPage <= 1 ? "disabled" : ""
          }>&lsaquo;</button>
          <span class="pager-state">${state.ingestHistoryPage} / ${totalPages}</span>
          <button class="btn btn-ghost pager-btn" type="button" data-ingest-page="next" ${
            state.ingestHistoryPage >= totalPages ? "disabled" : ""
          }>&rsaquo;</button>
        </div>
      </div>
    </div>
  `;
}

function applySuccessfulIngestState(result, request) {
  const nextTimestampOrder = String((request.timestamp_order || 1) + 1);
  elements.ingestContent.value = "";
  elements.ingestEpisodeId.value = result.episode_id;
  elements.ingestTimestampOrder.value = nextTimestampOrder;
  resetIngestHistoryNavigation();
  syncIngestFieldHints(
    `刚保存了这个分组里的第 ${request.timestamp_order} 条内容，下一条已自动准备为 ${nextTimestampOrder}。`,
  );
  elements.ingestContent.focus();
}

function navigateIngestHistory(direction) {
  const history = getIngestInputHistory();
  if (!history.length) {
    return;
  }

  if (state.ingestHistoryCursor === -1) {
    state.ingestDraftSnapshot = elements.ingestContent.value;
  }

  const nextCursor = state.ingestHistoryCursor + direction;
  if (nextCursor < 0) {
    state.ingestHistoryCursor = -1;
    elements.ingestContent.value = state.ingestDraftSnapshot;
    return;
  }

  if (nextCursor >= history.length) {
    state.ingestHistoryCursor = history.length - 1;
  } else {
    state.ingestHistoryCursor = nextCursor;
  }

  elements.ingestContent.value = history[state.ingestHistoryCursor];
  const end = elements.ingestContent.value.length;
  elements.ingestContent.setSelectionRange(end, end);
}

function renderRetrieveResult(result) {
  const candidates = result.candidates || [];
  const summary = result.evidence_summary
    ? formatValue(result.evidence_summary)
    : "系统已按你的问题完成查找。";
  elements.retrieveResult.innerHTML = `
    <div class="status ${candidates.length ? "status-ok" : "status-warn"}">
      共找到 ${escapeHtml(result.candidate_count)} 条可能相关的记录
    </div>
    <div class="result-grid">
      <div class="result-block">
        <h3>查找说明</h3>
        <p class="meta">${escapeHtml(summary)}</p>
      </div>
      <div class="result-block">
        <h3>相关内容</h3>
        <ul class="stack-list">
          ${candidates
            .map(
              (candidate) => `
                <li>
                  <strong>内容编号：${escapeHtml(candidate.object_id)}</strong>
                  <div class="meta">内容类型：${escapeHtml(localizeContentType(candidate.object_type))} / 匹配程度：${escapeHtml(candidate.score ?? "暂无")}</div>
                  <div>${escapeHtml(candidate.content_preview || "这条记录暂时没有可预览的内容。")}</div>
                </li>
              `,
            )
            .join("") || "<li>这次没有找到相关内容。</li>"}
        </ul>
      </div>
    </div>
  `;
}

function renderAccessResult(result) {
  const candidateObjects = result.candidate_objects || [];
  const selectedObjects = result.selected_objects || [];
  const answer = result.answer || null;
  const answerTrace = answer?.trace || null;
  const supportIds = answer?.support_ids || [];
  elements.accessResult.innerHTML = `
    <div class="status ${selectedObjects.length ? "status-ok" : "status-warn"}">
      本次回答参考了 ${escapeHtml(result.selected_count)} 条内容
    </div>
    <div class="result-grid">
      <div class="result-block">
        <h3>回答详情</h3>
        <p class="meta">${escapeHtml(answer?.text || result.summary || "系统已整理好这次回答。")}</p>
        ${renderMetricList([
          { label: "参考范围", value: result.context_object_count },
          { label: "可参考内容", value: result.candidate_count },
          { label: "实际采用", value: result.selected_count },
          { label: "回答方式", value: localizeAccessDepth(result.resolved_depth) },
          { label: "回答来源", value: localizeProviderFamily(answerTrace?.provider_family) },
          { label: "回答依据", value: supportIds.length },
        ])}
        ${answerTrace?.fallback_used
          ? `<p class="meta">已触发回退：${escapeHtml(answerTrace.fallback_reason || "provider 不可用，已改用确定性路径。")}</p>`
          : ""}
        ${supportIds.length
          ? `<p class="meta">依据对象：${escapeHtml(supportIds.join(", "))}</p>`
          : ""}
      </div>
      <div class="result-block">
        <h3>可参考内容</h3>
        <ul class="stack-list">
          ${candidateObjects
            .map(
              (item) => `
                <li>
                  <strong>内容编号：${escapeHtml(item.object_id)}</strong>
                  <div class="meta">内容类型：${escapeHtml(localizeContentType(item.object_type))} / 记录分组：${escapeHtml(item.episode_id || "未指定")}</div>
                  <div>${escapeHtml(item.preview || "这条记录暂时没有可预览的内容。")}</div>
                </li>
              `,
            )
            .join("") || "<li>这次没有可参考的内容。</li>"}
        </ul>
      </div>
      <div class="result-block">
        <h3>回答采用内容</h3>
        <ul class="stack-list">
          ${selectedObjects
            .map(
              (item) => `
                <li>
                  <strong>内容编号：${escapeHtml(item.object_id)}</strong>
                  <div class="meta">内容类型：${escapeHtml(localizeContentType(item.object_type))} / 记录分组：${escapeHtml(item.episode_id || "未指定")}</div>
                  <div>${escapeHtml(item.preview || "这条记录暂时没有可预览的内容。")}</div>
                </li>
              `,
            )
            .join("") || "<li>这次没有采用任何内容。</li>"}
        </ul>
      </div>
    </div>
  `;
}

function renderOfflineResult(result) {
  elements.offlineResult.innerHTML = `
    <div class="status status-ok">后台任务已提交，稍后可回来查看。</div>
    ${renderMetricList([
      { label: "任务编号", value: result.job_id },
      { label: "当前状态", value: result.status },
    ])}
  `;
}

function renderDebugTimeline(result) {
  const timeline = result.timeline || [];
  const deltas = result.object_deltas || [];
  const contextViews = result.context_views || [];
  const evidenceViews = result.evidence_views || [];
  elements.debugResult.innerHTML = `
    <div class="status ${timeline.length ? "status-ok" : "status-warn"}">
      共找到 ${timeline.length} 条处理记录
    </div>
    <div class="timeline-list">
      ${timeline
        .map(
          (event) => `
            <article class="event-card">
              <h3>${escapeHtml(event.label)}</h3>
              <p class="meta">范围：${escapeHtml(event.scope)} / 类型：${escapeHtml(event.kind)}</p>
              <p>${escapeHtml(event.summary)}</p>
              <p class="meta">${escapeHtml(formatDateTime(event.occurred_at))}</p>
            </article>
          `,
        )
        .join("") || '<div class="empty-state">这次没有找到相关处理记录。</div>'}
    </div>
    <div class="result-panel">
      <h3>内容变化</h3>
      <ul class="notes-list">
        ${deltas
          .map(
            (delta) => `
              <li>内容编号：${escapeHtml(delta.object_id)} / 第 ${escapeHtml(delta.object_version)} 版 / ${escapeHtml(delta.summary)}</li>
            `,
          )
          .join("") || "<li>这次范围内没有发现内容变化。</li>"}
      </ul>
    </div>
    <div class="result-panel">
      <h3>选择依据</h3>
      <ul class="stack-list">
        ${contextViews
          .map(
            (view) => `
              <li>
                <strong>${escapeHtml(view.context_kind)}</strong>
                <div class="meta">处理编号：${escapeHtml(view.operation_id)} / 查看范围：${escapeHtml(view.workspace_id || "当前页面")}</div>
                <div>${escapeHtml(view.summary)}</div>
                <div class="meta">关联内容：${escapeHtml((view.context_object_ids || []).join(", ") || "无")}</div>
                <div class="meta">实际采用：${escapeHtml((view.selected_object_ids || []).join(", ") || "无")}</div>
              </li>
            `,
          )
          .join("") || "<li>这次范围内没有选择依据记录。</li>"}
      </ul>
    </div>
    <div class="result-panel">
      <h3>参考依据</h3>
      <ul class="stack-list">
        ${evidenceViews
          .map(
            (view) => `
              <li>
                <strong>内容编号：${escapeHtml(view.object_id)}</strong>
                <div class="meta">内容类型：${escapeHtml(localizeContentType(view.object_type))} / ${view.selected ? "已用于本次结果" : "作为备选参考"}</div>
                <div>${escapeHtml(view.summary)}</div>
                <div class="meta">相关程度：${escapeHtml(view.score ?? "暂无")} / 优先顺序：${escapeHtml(view.priority ?? "暂无")}</div>
                <div class="meta">引用来源：${escapeHtml((view.evidence_refs || []).join(", ") || "无")}</div>
              </li>
            `,
          )
          .join("") || "<li>这次范围内没有参考依据记录。</li>"}
      </ul>
    </div>
  `;
}

function fillSelect(select, values, selectedValue) {
  select.innerHTML = (values || [])
    .map((item) => {
      const value = typeof item === "string" ? item : item.value;
      const label = typeof item === "string" ? item : item.label;
      return `<option value="${escapeHtml(value)}"${value === selectedValue ? " selected" : ""}>${escapeHtml(label)}</option>`;
    })
    .join("");
}

function setPanelLocked(panel, locked, message) {
  panel.classList.toggle("panel-disabled", locked);
  panel.querySelectorAll("button, input, select, textarea").forEach((control) => {
    control.disabled = locked;
  });
  const note = panel.querySelector("[data-gate-note]");
  if (note && message) {
    note.textContent = message;
  }
}

function syncOfflineMode() {
  const reflectEpisode = elements.offlineJobKind.value === "reflect_episode";
  const locked = !state.apiKey;
  elements.offlineEpisodeId.disabled = locked || !reflectEpisode;
  elements.offlineFocus.disabled = locked || !reflectEpisode;
  elements.offlineTargetRefs.disabled = locked || reflectEpisode;
  elements.offlineReason.disabled = locked || reflectEpisode;
  elements.offlineModeNote.textContent = reflectEpisode
    ? "当前会整理某个记录分组，请填写分组编号；聚焦主题可选。"
    : "当前会整理多条内容并提炼长期规则，请至少填写两条内容编号和任务说明。";
  syncActionAvailability();
}

function syncDebugGuard() {
  const hasApiKey = Boolean(state.apiKey);
  const devModeEnabled = Boolean(state.settingsPage?.runtime?.dev_mode);
  if (!hasApiKey) {
    elements.debugGuardStatus.textContent =
      "请先连接后再进入问题排查。";
    return;
  }
  elements.debugGuardStatus.textContent = devModeEnabled
    ? "问题排查已开启，可查看处理记录、内容变化和参考依据。"
    : "如需查看处理过程，请先在设置中开启高级排查。";
}

function syncPanelGuards() {
  const hasApiKey = Boolean(state.apiKey);

  elements.authRequiredPanels.forEach((panel) => {
    setPanelLocked(
      panel,
      !hasApiKey,
      hasApiKey ? panel.dataset.readyMessage : panel.dataset.lockMessage,
    );
  });

  const devModeEnabled = Boolean(state.settingsPage?.runtime?.dev_mode);
  elements.devRequiredPanels.forEach((panel) => {
    if (!hasApiKey) {
      return;
    }
    setPanelLocked(
      panel,
      !devModeEnabled,
      devModeEnabled ? panel.dataset.devReadyMessage : panel.dataset.devLockMessage,
    );
  });

  syncOfflineMode();
  syncDebugGuard();
  syncActionAvailability();
}

function resetIngestForm() {
  elements.ingestForm.reset();
  elements.ingestTimestampOrder.value = DEFAULTS.ingestTimestampOrder;
  resetIngestHistoryNavigation();
  syncIngestFieldHints();
  elements.ingestContent.focus();
}

function resetRetrieveForm() {
  elements.retrieveForm.reset();
  elements.retrieveMaxCandidates.value = DEFAULTS.retrieveMaxCandidates;
  elements.retrieveResult.innerHTML = '<div class="empty-state">还没有查找结果。</div>';
  syncActionAvailability();
}

function resetAccessForm() {
  elements.accessForm.reset();
  elements.accessDepth.value = "auto";
  elements.accessResult.innerHTML = '<div class="empty-state">还没有回答结果。</div>';
  syncActionAvailability();
}

function resetOfflineForm() {
  elements.offlineForm.reset();
  elements.offlineJobKind.value = "reflect_episode";
  elements.offlinePriority.value = DEFAULTS.offlinePriority;
  elements.offlineResult.innerHTML = '<div class="empty-state">还没有提交后台任务。</div>';
  syncOfflineMode();
}

function resetSettingsForm() {
  elements.settingsForm.reset();
  elements.settingsResult.innerHTML = state.settingsPage
    ? ""
    : '<div class="empty-state">连接后会在这里显示当前工作方式和即时生效状态。</div>';
  if (state.settingsPage) {
    renderSettingsOptions(state.settingsPage);
    renderSettingsPage(state.settingsPage);
  }
  renderLlmPage();
  syncActionAvailability();
}

function resetDebugForm() {
  elements.debugForm.reset();
  elements.debugLimit.value = DEFAULTS.debugLimit;
  elements.debugResult.innerHTML = '<div class="empty-state">还没有排查结果。</div>';
  syncActionAvailability();
}

function clearLoadedState() {
  state.catalogPage = null;
  state.gateDemoPage = null;
  state.settingsPage = null;
  state.llmEditorDraft = null;
  state.llmServiceModelSelections = {};
  state.llmNotice = null;
  setLlmModalOpen(false);
  resetOperationChain();
  renderOverviewEmpty("连接后可查看当前状态和主要入口。");
  renderGateDemoEmpty("连接后可查看补充说明。");
  resetIngestForm();
  resetRetrieveForm();
  resetAccessForm();
  resetOfflineForm();
  resetSettingsForm();
  resetDebugForm();
  updateShellSignals();
  syncPanelGuards();
  renderOperationChain(state.activeOperation);
}

function collectIngestRequest() {
  const content = elements.ingestContent.value.trim();
  if (!content) {
    throw new Error("请先填写要写入的内容");
  }
  if (!isPositiveInteger(elements.ingestTimestampOrder.value)) {
    throw new Error("时间顺序需要填写大于 0 的整数。");
  }
  const body = {
    content,
    timestamp_order: Number.parseInt(elements.ingestTimestampOrder.value, 10),
  };
  if (elements.ingestEpisodeId.value.trim()) {
    body.episode_id = elements.ingestEpisodeId.value.trim();
  }
  return body;
}

function collectRetrieveRequest() {
  const query = elements.retrieveQuery.value.trim();
  if (!query) {
    throw new Error("请先填写想查找的问题");
  }
  if (!isPositiveInteger(elements.retrieveMaxCandidates.value)) {
    throw new Error("最多显示需要填写大于 0 的整数。");
  }
  const body = {
    query,
    max_candidates: Number.parseInt(elements.retrieveMaxCandidates.value, 10),
  };
  if (elements.retrieveEpisodeId.value.trim()) {
    body.episode_id = elements.retrieveEpisodeId.value.trim();
  }
  return body;
}

function collectAccessRequest() {
  const query = elements.accessQuery.value.trim();
  if (!query) {
    throw new Error("请先填写你的问题");
  }
  const body = {
    query,
    depth: elements.accessDepth.value,
    explain: elements.accessExplain.checked,
  };
  if (elements.accessEpisodeId.value.trim()) {
    body.episode_id = elements.accessEpisodeId.value.trim();
  }
  if (elements.accessTaskId.value.trim()) {
    body.task_id = elements.accessTaskId.value.trim();
  }
  return body;
}

function collectOfflineRequest() {
  const jobKind = elements.offlineJobKind.value;
  const priority = Number.parseFloat(elements.offlinePriority.value);
  const body = {
    job_kind: jobKind,
    priority: Number.isFinite(priority) ? priority : 0.5,
  };

  if (jobKind === "reflect_episode") {
    const episodeId = elements.offlineEpisodeId.value.trim();
    const focus = elements.offlineFocus.value.trim();
    if (!episodeId) {
      throw new Error("整理当前分组时，需要填写记录分组。");
    }
    body.payload = {
      episode_id: episodeId,
      focus: focus || "整理这组内容",
    };
    return body;
  }

  const targetRefs = getOfflineTargetRefs();
  const reason = elements.offlineReason.value.trim();
  if (targetRefs.length < 2) {
    throw new Error("提炼长期规则时，至少需要填写两条目标内容编号。");
  }
  if (!reason) {
    throw new Error("提炼长期规则时，需要填写任务说明。");
  }
  body.payload = {
    target_refs: targetRefs,
    reason,
  };
  return body;
}

function collectSettingsApplyRequest() {
  const answerMode = elements.settingsProvider.value || "builtin";
  if (answerMode === "builtin") {
    return {
      provider: "stub",
      model: "deterministic",
      dev_mode: Boolean(elements.settingsDevMode.checked),
    };
  }
  const llmRequest = buildSelectedLlmApplyRequest({ includeDevMode: true });
  if (!llmRequest) {
    throw new Error("请先在 LLM 配置里保存一项服务，并获取可用模型。");
  }
  return llmRequest;
}

function collectDebugRequest() {
  const body = {
    limit: Number.parseInt(elements.debugLimit.value, 10) || 80,
    include_state_deltas: true,
  };
  if (elements.debugRunId.value.trim()) {
    body.run_id = elements.debugRunId.value.trim();
  }
  if (elements.debugOperationId.value.trim()) {
    body.operation_id = elements.debugOperationId.value.trim();
  }
  if (elements.debugObjectId.value.trim()) {
    body.object_id = elements.debugObjectId.value.trim();
  }
  return body;
}

async function refreshOverview() {
  if (!state.apiKey) {
    state.catalogPage = null;
    state.settingsPage = null;
    state.llmNotice = null;
    renderOverviewEmpty("连接后可查看当前状态和主要入口。");
    resetSettingsForm();
    updateShellSignals();
    syncPanelGuards();
    renderOperationChain(state.activeOperation);
    return;
  }

  const [catalog, settings] = await Promise.all([
    loadCatalog(state.apiKey),
    loadSettings(state.apiKey),
  ]);
  state.catalogPage = catalog;
  state.settingsPage = settings;
  renderOverview(catalog, settings);
  renderSettingsOptions(settings);
  renderSettingsPage(settings);
  renderLlmPage();
  updateShellSignals();
  syncPanelGuards();
  renderOperationChain(state.activeOperation);
}

async function refreshGateDemo() {
  if (!state.apiKey) {
    state.gateDemoPage = null;
    renderGateDemoEmpty("连接后可查看补充说明。");
    updateShellSignals();
    return;
  }

  const page = await loadGateDemo(state.apiKey);
  state.gateDemoPage = page;
  renderGateDemo(page);
  updateShellSignals();
}

async function refreshWorkspaceData() {
  if (!state.apiKey) {
    renderOverviewEmpty("连接后可查看当前状态和主要入口。");
    renderGateDemoEmpty("连接后可查看补充说明。");
    updateShellSignals();
    syncPanelGuards();
    return;
  }
  await Promise.all([refreshOverview(), refreshGateDemo()]);
}

elements.workspaceTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    setActiveWorkspace(tab.dataset.workspaceTarget || DEFAULTS.workspace);
  });
});

elements.overviewGrid.addEventListener("click", (event) => {
  const target = event.target instanceof Element
    ? event.target.closest("[data-overview-entrypoint]")
    : null;
  if (!(target instanceof HTMLButtonElement)) {
    return;
  }
  jumpToOverviewEntrypoint(target.dataset.overviewEntrypoint || "");
});

elements.operationTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    setActiveOperation(tab.dataset.operationTarget || DEFAULTS.operation);
  });
});

elements.opsChainOpenButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const operationId = button.dataset.openChain || DEFAULTS.operation;
    handleOperationChainOpenButton(operationId, setActiveWorkspace, setActiveOperation);
  });
});

elements.opsChainBody.addEventListener("click", (event) => {
  handleOperationChainBodyClick(event);
});

if (elements.opsChainClose) {
  elements.opsChainClose.addEventListener("click", () => {
    if (window.innerWidth <= 1024) {
      setOperationChainDrawerOpen(false);
      return;
    }
    setOperationChainHidden(true);
  });
}

if (elements.opsChainBackdrop) {
  elements.opsChainBackdrop.addEventListener("click", () => {
    setOperationChainDrawerOpen(false);
  });
}

if (elements.opsChainRestore) {
  elements.opsChainRestore.addEventListener("click", () => {
    setOperationChainHidden(false);
    renderOperationChain(state.activeOperation);
    focusOperationChainShell();
  });
}

bindFormAction(elements.authForm, "auth-connect", {
  button: elements.authSubmit,
  busyLabel: "连接中",
  minBusyMs: MIN_BUSY_MS.auth,
  work: async () => {
    state.apiKey = elements.apiKey.value.trim();
    if (state.apiKey) {
      window.localStorage.setItem(STORAGE_KEY, state.apiKey);
      updateShellSignals();
      syncPanelGuards();
      await refreshWorkspaceData();
      return;
    }
    window.localStorage.removeItem(STORAGE_KEY);
    clearLoadedState();
    navigate(
      {
        activeWorkspace: DEFAULTS.workspace,
        activeOperation: DEFAULTS.operation,
        activeSettingsSection: DEFAULTS.settingsSection,
      },
      { replace: true },
    );
    setStatus("当前还没有连接。");
  },
});

bindClickAction(elements.clearKey, "auth-clear", {
  busyLabel: "清除中",
  minBusyMs: MIN_BUSY_MS.reset,
  work: async () => {
    state.apiKey = "";
    elements.apiKey.value = "";
    window.localStorage.removeItem(STORAGE_KEY);
    clearLoadedState();
    navigate(
      {
        activeWorkspace: DEFAULTS.workspace,
        activeOperation: DEFAULTS.operation,
        activeSettingsSection: DEFAULTS.settingsSection,
      },
      { replace: true },
    );
    setStatus("当前还没有连接。");
  },
});

bindClickAction(elements.reloadOverview, "overview-refresh", {
  before: () => {
    setActiveWorkspace("workspace-overview");
  },
  busyLabel: "同步中",
  minBusyMs: MIN_BUSY_MS.refresh,
  work: refreshWorkspaceData,
});

bindClickAction(elements.loadGateDemo, "gate-demo-refresh", {
  before: () => {
    setActiveWorkspace("workspace-overview");
  },
  busyLabel: "刷新中",
  minBusyMs: MIN_BUSY_MS.refresh,
  work: refreshGateDemo,
});

bindFormAction(elements.ingestForm, "ingest-submit", {
  button: elements.ingestSubmit,
  before: () => {
    navigate({
      activeWorkspace: "workspace-operations",
      activeOperation: "module-ingest",
    });
  },
  busyLabel: "写入中",
  minBusyMs: MIN_BUSY_MS.submit,
  readyMessage: "写入完成，已保存到本地历史。",
  work: async () => {
    const request = collectIngestRequest();
    const submittedAt = new Date().toISOString();
    setOperationChainSnapshot("module-ingest", buildRunningOperationChain("module-ingest", request, submittedAt));
    try {
      const result = await submitIngest(state.apiKey, request);
      rememberIngestSubmission(result, request);
      renderIngestHistory();
      applySuccessfulIngestState(result, request);
      setOperationChainSnapshot("module-ingest", buildSuccessfulOperationChain("module-ingest", request, result, submittedAt));
    } catch (error) {
      setOperationChainSnapshot("module-ingest", buildErrorOperationChain("module-ingest", request, error, submittedAt));
      throw error;
    }
  },
});

bindClickAction(elements.ingestReset, "ingest-reset", {
  busyLabel: "重置中",
  minBusyMs: MIN_BUSY_MS.reset,
  work: async () => {
    resetIngestForm();
  },
});

bindFormAction(elements.retrieveForm, "retrieve-submit", {
  button: elements.retrieveSubmit,
  before: () => {
    navigate({
      activeWorkspace: "workspace-operations",
      activeOperation: "module-retrieve",
    });
  },
  busyLabel: "检索中",
  minBusyMs: MIN_BUSY_MS.submit,
  work: async () => {
    const request = collectRetrieveRequest();
    const submittedAt = new Date().toISOString();
    setOperationChainSnapshot("module-retrieve", buildRunningOperationChain("module-retrieve", request, submittedAt));
    try {
      const result = await submitRetrieve(state.apiKey, request);
      renderRetrieveResult(result);
      setOperationChainSnapshot("module-retrieve", buildSuccessfulOperationChain("module-retrieve", request, result, submittedAt));
    } catch (error) {
      setOperationChainSnapshot("module-retrieve", buildErrorOperationChain("module-retrieve", request, error, submittedAt));
      throw error;
    }
  },
});

bindClickAction(elements.retrieveReset, "retrieve-reset", {
  busyLabel: "重置中",
  minBusyMs: MIN_BUSY_MS.reset,
  work: async () => {
    resetRetrieveForm();
  },
});

bindFormAction(elements.accessForm, "access-submit", {
  button: elements.accessSubmit,
  before: () => {
    navigate({
      activeWorkspace: "workspace-operations",
      activeOperation: "module-access",
    });
  },
  busyLabel: "访问中",
  minBusyMs: MIN_BUSY_MS.submit,
  work: async () => {
    const request = collectAccessRequest();
    const submittedAt = new Date().toISOString();
    setOperationChainSnapshot("module-access", buildRunningOperationChain("module-access", request, submittedAt));
    try {
      const result = await submitAccess(state.apiKey, request);
      renderAccessResult(result);
      setOperationChainSnapshot("module-access", buildSuccessfulOperationChain("module-access", request, result, submittedAt));
    } catch (error) {
      setOperationChainSnapshot("module-access", buildErrorOperationChain("module-access", request, error, submittedAt));
      throw error;
    }
  },
});

bindClickAction(elements.accessReset, "access-reset", {
  busyLabel: "重置中",
  minBusyMs: MIN_BUSY_MS.reset,
  work: async () => {
    resetAccessForm();
  },
});

bindFormAction(elements.offlineForm, "offline-submit", {
  button: elements.offlineSubmit,
  before: () => {
    navigate({
      activeWorkspace: "workspace-operations",
      activeOperation: "module-offline",
    });
  },
  busyLabel: "提交中",
  minBusyMs: MIN_BUSY_MS.submit,
  work: async () => {
    const request = collectOfflineRequest();
    const submittedAt = new Date().toISOString();
    setOperationChainSnapshot("module-offline", buildRunningOperationChain("module-offline", request, submittedAt));
    try {
      const result = await submitOffline(state.apiKey, request);
      renderOfflineResult(result);
      setOperationChainSnapshot("module-offline", buildSuccessfulOperationChain("module-offline", request, result, submittedAt));
    } catch (error) {
      setOperationChainSnapshot("module-offline", buildErrorOperationChain("module-offline", request, error, submittedAt));
      throw error;
    }
  },
});

bindClickAction(elements.offlineReset, "offline-reset", {
  busyLabel: "重置中",
  minBusyMs: MIN_BUSY_MS.reset,
  work: async () => {
    resetOfflineForm();
  },
});
elements.offlineJobKind.addEventListener("change", syncOfflineMode);

function setSettingsControlsBusy(busy) {
  const locked = busy || !state.apiKey;
  elements.settingsProvider.disabled = locked;
  elements.settingsDevMode.disabled = locked;
}

async function applySettingsLive() {
  if (!state.apiKey || !state.settingsPage) {
    return;
  }
  setActiveWorkspace("workspace-settings");
  setSettingsControlsBusy(true);
  const result = await runUiAction("settings-apply-live", {
    busyLabel: "应用中",
    minBusyMs: MIN_BUSY_MS.mutate,
    readyMessage: "设置已立即生效。",
    work: async () => {
      const body = collectSettingsApplyRequest();
      const mutation = await applySettings(state.apiKey, body);
      const refreshedSettings = await loadSettings(state.apiKey);
      state.settingsPage = refreshedSettings;
      renderSettingsOptions(refreshedSettings);
      if (state.catalogPage) {
        renderOverview(state.catalogPage, refreshedSettings);
      }
      renderSettingsMutation(mutation, refreshedSettings);
      updateShellSignals();
      syncPanelGuards();
      renderOperationChain(state.activeOperation);
    },
  });
  setSettingsControlsBusy(false);
  renderLlmPage();
  syncPanelGuards();
  return result;
}

elements.settingsForm.addEventListener("submit", (event) => {
  event.preventDefault();
});
elements.settingsProvider.addEventListener("change", () => {
  if (elements.settingsProvider.value === "llm" && !buildSelectedLlmApplyRequest()) {
    elements.settingsProvider.value = getAnswerModeFromSettings(state.settingsPage);
    renderSettingsPage(state.settingsPage, "请先在 LLM 配置里保存服务，并获取可用模型。", "status-warn");
    navigate({
      activeWorkspace: "workspace-settings",
      activeSettingsSection: "settings-panel-llm",
    });
    syncActionAvailability();
    return;
  }
  void applySettingsLive();
});
elements.settingsDevMode.addEventListener("change", () => {
  void applySettingsLive();
});

elements.settingsTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    setActiveSettingsSection(tab.dataset.settingsTarget || DEFAULTS.settingsSection);
  });
});

bindClickAction(elements.llmCreateService, "llm-editor-open", {
  before: () => {
    navigate({
      activeWorkspace: "workspace-settings",
      activeSettingsSection: "settings-panel-llm",
    });
  },
  busyLabel: "打开中",
  minBusyMs: MIN_BUSY_MS.reset,
  readyMessage: "可以继续编辑服务。",
  work: async () => {
    openLlmEditor({ protocol: getSelectedLlmDraft().protocol || "openai" });
  },
});

elements.llmProtocolGrid.addEventListener("click", (event) => {
  const protocolCard = event.target.closest("[data-llm-protocol]");
  if (!(protocolCard instanceof HTMLElement)) {
    return;
  }
  const protocol = protocolCard.dataset.llmProtocol || "openai";
  primeLlmEditorFromSettings(state.settingsPage, { protocol });
  renderLlmPage("已切换协议模板。", "status-ok");
});

elements.llmServiceForm.addEventListener("submit", (event) => {
  event.preventDefault();
});

elements.llmServiceName.addEventListener("input", () => {
  updateLlmEditorDraft({ name: elements.llmServiceName.value });
  syncLlmEditorDraftUi();
  renderLlmIconPreview();
  renderLlmStatus("服务名称已修改，点击“保存服务”后才会生效。", "status-warn");
  syncActionAvailability();
});

elements.llmIconUpload.addEventListener("click", () => {
  elements.llmServiceIconFile.click();
});

elements.llmServiceIconFile.addEventListener("change", async () => {
  const [file] = elements.llmServiceIconFile.files || [];
  if (!file) {
    return;
  }
  try {
    await updateDraftIconFromFile(file);
  } catch (error) {
    renderLlmStatus(error instanceof Error ? error.message : "图标图片处理失败。", "status-err");
  } finally {
    elements.llmServiceIconFile.value = "";
  }
});

elements.llmIconRemove.addEventListener("click", () => {
  updateLlmEditorDraft({ icon: "" });
  elements.llmServiceIcon.value = "";
  syncLlmEditorDraftUi();
  renderLlmIconPreview();
  renderLlmStatus("已移除图片图标，保存后会回退为服务名称首字母。", "status-warn");
  syncActionAvailability();
});

elements.llmServiceEndpoint.addEventListener("input", () => {
  updateLlmEditorDraft({ endpoint: elements.llmServiceEndpoint.value });
  syncLlmEditorDraftUi();
  renderLlmStatus("服务地址已修改，点击“保存服务”后才会生效。", "status-warn");
  syncActionAvailability();
});

elements.llmServiceApiKey.addEventListener("input", () => {
  updateLlmEditorDraft({ apiKey: elements.llmServiceApiKey.value });
  syncLlmEditorDraftUi();
  renderLlmStatus("Key 已修改，点击“保存服务”后才会生效。", "status-warn");
  syncActionAvailability();
});

elements.llmActiveModel.addEventListener("change", () => {
  updateLlmEditorDraft({ model: elements.llmActiveModel.value });
  syncLlmEditorDraftUi();
  renderLlmStatus("活跃模型已修改，点击“保存服务”后才会生效。", "status-warn");
  syncActionAvailability();
});

bindClickAction(elements.llmServiceSave, "llm-service-save", {
  before: () => {
    navigate({
      activeWorkspace: "workspace-settings",
      activeSettingsSection: "settings-panel-llm",
    });
  },
  busyLabel: "保存中",
  minBusyMs: MIN_BUSY_MS.mutate,
  readyMessage: "服务已保存。",
  work: async () => {
    await saveCurrentLlmService();
    closeLlmEditor();
  },
});

bindClickAction(elements.llmServiceDiscover, "llm-service-discover", {
  before: () => {
    navigate({
      activeWorkspace: "workspace-settings",
      activeSettingsSection: "settings-panel-llm",
    });
  },
  busyLabel: "获取中",
  minBusyMs: MIN_BUSY_MS.refresh,
  readyMessage: "模型列表已刷新。",
  work: async () => {
    await discoverModelsFromEditor();
  },
});

elements.llmServiceDelete.addEventListener("click", () => {
  const draft = getSelectedLlmDraft();
  const service = draft.serviceId ? getLlmServiceById(draft.serviceId) : null;
  if (!service || !confirmDeleteLlmService(service)) {
    return;
  }
  void runUiAction(`llm-delete-${service.service_id}`, {
    button: elements.llmServiceDelete,
    busyLabel: "删除中",
    minBusyMs: MIN_BUSY_MS.mutate,
    readyMessage: service.is_active ? "已删除服务，并切回内建模式。" : "服务已删除。",
    work: async () => {
      await deleteSavedLlmService(service.service_id, { closeEditor: true });
    },
  });
});

bindClickAction(elements.llmEditorReset, "llm-editor-reset", {
  before: () => {
    navigate({
      activeWorkspace: "workspace-settings",
      activeSettingsSection: "settings-panel-llm",
    });
  },
  busyLabel: "切换中",
  minBusyMs: MIN_BUSY_MS.reset,
  readyMessage: "已切回新建服务。",
  work: async () => {
    const currentProtocol = getSelectedLlmDraft().protocol || "openai";
    primeLlmEditorFromSettings(state.settingsPage, { protocol: currentProtocol });
    setLlmModalOpen(true);
    renderLlmPage("已切回新建服务。", "status-ok");
  },
});

bindClickAction(elements.llmEditorClose, "llm-editor-close", {
  busyLabel: "关闭中",
  minBusyMs: MIN_BUSY_MS.reset,
  readyMessage: "可以继续操作。",
  work: async () => {
    closeLlmEditor();
  },
});

elements.llmModalCloseTargets.forEach((target) => {
  target.addEventListener("click", () => {
    closeLlmEditor();
  });
});

elements.llmTraceClose.addEventListener("click", () => {
  closeLlmTraceModal();
});

elements.llmTraceModalCloseTargets.forEach((target) => {
  target.addEventListener("click", () => {
    closeLlmTraceModal();
  });
});

elements.llmServiceList.addEventListener("change", (event) => {
  const modelSelect = event.target.closest("[data-llm-service-model]");
  if (!(modelSelect instanceof HTMLSelectElement)) {
    return;
  }
  state.llmServiceModelSelections[modelSelect.dataset.llmServiceModel] = modelSelect.value;
  renderLlmStatus("已选择待启用的模型。", "status-ok");
  syncActionAvailability();
});

elements.llmServiceList.addEventListener("click", (event) => {
  const editButton = event.target.closest("[data-llm-edit-service]");
  if (editButton instanceof HTMLElement) {
    openLlmEditor(
      { serviceId: editButton.dataset.llmEditService },
      "已载入这项服务，可继续修改。",
      "status-ok",
    );
    return;
  }

  const discoverButton = event.target.closest("[data-llm-discover-service]");
  if (discoverButton instanceof HTMLButtonElement) {
    void runUiAction(`llm-discover-${discoverButton.dataset.llmDiscoverService}`, {
      button: discoverButton,
      busyLabel: "获取中",
      minBusyMs: MIN_BUSY_MS.refresh,
      readyMessage: "模型列表已刷新。",
      work: async () => {
        await discoverModelsForService(discoverButton.dataset.llmDiscoverService);
      },
    });
    return;
  }

  const deleteButton = event.target.closest("[data-llm-delete-service]");
  if (deleteButton instanceof HTMLButtonElement) {
    const service = getLlmServiceById(deleteButton.dataset.llmDeleteService);
    if (!service || !confirmDeleteLlmService(service)) {
      return;
    }
    void runUiAction(`llm-delete-${deleteButton.dataset.llmDeleteService}`, {
      button: deleteButton,
      busyLabel: "删除中",
      minBusyMs: MIN_BUSY_MS.mutate,
      readyMessage: service.is_active ? "已删除服务，并切回内建模式。" : "服务已删除。",
      work: async () => {
        await deleteSavedLlmService(deleteButton.dataset.llmDeleteService);
      },
    });
    return;
  }

  const activateButton = event.target.closest("[data-llm-activate-service]");
  if (activateButton instanceof HTMLButtonElement) {
    void runUiAction(`llm-activate-${activateButton.dataset.llmActivateService}`, {
      button: activateButton,
      busyLabel: "启用中",
      minBusyMs: MIN_BUSY_MS.mutate,
      readyMessage: "已切换到这项服务。",
      work: async () => {
        await activateSavedLlmService(activateButton.dataset.llmActivateService);
      },
    });
  }
});

window.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") {
    return;
  }
  if (handleOperationChainEscape()) {
    return;
  }
  if (state.llmModalOpen) {
    closeLlmEditor();
  }
});

window.addEventListener("resize", () => {
  syncOperationChainVisibility();
  if (window.innerWidth > 1024 && state.operationChainDrawerOpen) {
    setOperationChainDrawerOpen(false);
  }
});

bindFormAction(elements.debugForm, "debug-submit", {
  button: elements.debugSubmit,
  before: () => {
    setActiveWorkspace("workspace-debug");
  },
  busyLabel: "加载中",
  minBusyMs: MIN_BUSY_MS.submit,
  work: async () => {
    const body = collectDebugRequest();
    if (!body.run_id && !body.operation_id && !body.object_id) {
      throw new Error("请至少填写一个条件：请求编号、操作编号或内容编号。");
    }
    const result = await loadDebugTimeline(state.apiKey, body);
    renderDebugTimeline(result);
  },
});

bindClickAction(elements.debugReset, "debug-reset", {
  busyLabel: "重置中",
  minBusyMs: MIN_BUSY_MS.reset,
  work: async () => {
    resetDebugForm();
  },
});

elements.ingestContent.addEventListener("keydown", (event) => {
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
    return;
  }
  if (event.key === "ArrowUp") {
    const atTop =
      elements.ingestContent.selectionStart === 0
      && elements.ingestContent.selectionEnd === 0;
    if (state.ingestHistoryCursor !== -1 || atTop) {
      event.preventDefault();
      navigateIngestHistory(1);
    }
  }
  if (event.key === "ArrowDown") {
    const atBottom =
      elements.ingestContent.selectionStart === elements.ingestContent.value.length
      && elements.ingestContent.selectionEnd === elements.ingestContent.value.length;
    if (state.ingestHistoryCursor !== -1 || atBottom) {
      event.preventDefault();
      navigateIngestHistory(-1);
    }
  }
});

elements.ingestContent.addEventListener("input", () => {
  if (state.ingestHistoryCursor !== -1) {
    resetIngestHistoryNavigation();
  }
});

elements.ingestEpisodeId.addEventListener("input", () => {
  syncIngestFieldHints();
});

elements.ingestTimestampOrder.addEventListener("input", () => {
  syncIngestFieldHints();
});

elements.ingestResult.addEventListener("click", (event) => {
  const pagerButton = event.target.closest("[data-ingest-page]");
  if (!(pagerButton instanceof HTMLButtonElement)) {
    return;
  }
  const direction = pagerButton.dataset.ingestPage === "prev" ? -1 : 1;
  const totalPages = Math.max(1, Math.ceil(state.ingestSubmissionHistory.length / INGEST_PAGE_SIZE));
  state.ingestHistoryPage = clamp(state.ingestHistoryPage + direction, 1, totalPages);
  renderIngestHistory();
});

function bindAvailabilitySync(control) {
  if (!control) {
    return;
  }
  const eventName = control.tagName === "SELECT" || control.type === "checkbox"
    ? "change"
    : "input";
  control.addEventListener(eventName, syncActionAvailability);
}

[
  elements.apiKey,
  elements.ingestContent,
  elements.ingestEpisodeId,
  elements.ingestTimestampOrder,
  elements.retrieveQuery,
  elements.retrieveEpisodeId,
  elements.retrieveMaxCandidates,
  elements.accessQuery,
  elements.accessDepth,
  elements.accessEpisodeId,
  elements.accessTaskId,
  elements.accessExplain,
  elements.offlineJobKind,
  elements.offlineEpisodeId,
  elements.offlineFocus,
  elements.offlineTargetRefs,
  elements.offlineReason,
  elements.offlinePriority,
  elements.settingsProvider,
  elements.settingsDevMode,
  elements.llmServiceName,
  elements.llmServiceIcon,
  elements.llmServiceEndpoint,
  elements.llmServiceApiKey,
  elements.llmActiveModel,
  elements.debugRunId,
  elements.debugOperationId,
  elements.debugObjectId,
  elements.debugLimit,
].forEach(bindAvailabilitySync);

function closeSidebar() {
  elements.sidebarEl.classList.remove("is-open");
  elements.backdropEl.classList.remove("is-open");
}
if (elements.mobToggle) {
  elements.mobToggle.addEventListener("click", () => {
    const open = elements.sidebarEl.classList.toggle("is-open");
    elements.backdropEl.classList.toggle("is-open", open);
  });
}
if (elements.backdropEl) {
  elements.backdropEl.addEventListener("click", closeSidebar);
}
// Close sidebar when workspace tab clicked on mobile
elements.workspaceTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    if (window.innerWidth <= 1024) closeSidebar();
  });
});

elements.apiKey.value = state.apiKey;
workbenchRouter.initialize();
syncOperationChainVisibility();
renderIngestHistory();
syncIngestFieldHints();
renderLlmPage();
updateShellSignals();
syncPanelGuards();
syncActionAvailability();

if (state.apiKey) {
  setStatus("已就绪。");
  void runUiAction("startup-refresh", {
    minBusyMs: 0,
    work: refreshWorkspaceData,
  });
} else {
  setStatus("当前还没有连接。");
  renderOverviewEmpty("连接后可查看当前状态和主要入口。");
  renderGateDemoEmpty("连接后可查看补充说明。");
}
