import {
  applySettings,
  loadCatalog,
  loadDebugTimeline,
  loadGateDemo,
  loadSettings,
  previewSettings,
  restoreSettings,
  submitAccess,
  submitIngest,
  submitOffline,
  submitRetrieve,
} from "./api.js";

const STORAGE_KEY = "mind.frontend.apiKey";
const INGEST_HISTORY_KEY = "mind.frontend.ingestHistory.v1";
const INGEST_PAGE_SIZE = 10;
const MIN_BUSY_MS = {
  submit: 1000,
  mutate: 1000,
  refresh: 700,
  reset: 450,
  auth: 650,
};
const DEFAULTS = {
  ingestTimestampOrder: "1",
  retrieveMaxCandidates: "10",
  offlinePriority: "0.5",
  debugLimit: "80",
  workspace: "workspace-overview",
  operation: "module-ingest",
};

const ENTRYPOINT_LABELS = {
  ingest: { title: "写入记忆", mode: "保存", summary: "把重要内容保存下来，便于后续继续使用。" },
  retrieve: { title: "召回检索", mode: "查找", summary: "快速找回可能相关的已保存内容。" },
  access: { title: "访问问答", mode: "整理", summary: "整合已有内容，生成更完整的回答。" },
  offline: { title: "后台任务", mode: "整理", summary: "把整理任务交给系统在后台慢慢完成。" },
  gate_demo: { title: "示例摘要", mode: "查看", summary: "集中查看常用示例、检查结果和说明内容。" },
};

const GATE_ENTRY_LABELS = {
  demo_memory_flow: "记忆流演示",
  demo_access_flow: "访问流演示",
  demo_offline_flow: "离线流演示",
  gate_capability_readiness: "可用性检查",
  gate_telemetry_readiness: "记录完整性检查",
  report_provider_compatibility: "兼容性说明",
  report_telemetry_audit: "记录说明",
};

const GATE_KIND_LABELS = {
  demo: "演示",
  gate: "检查",
  report: "说明",
};

const VIEWPORT_LABELS = {
  desktop: "桌面端",
  mobile: "移动端",
};

const SETTING_LABELS = {
  backend: "存储方式",
  profile: "运行环境",
  provider: "回答方式",
  model: "模型名称",
  dev_mode: "高级排查",
};

const ACCESS_DEPTH_LABELS = {
  auto: "自动选择",
  flash: "快速回答",
  focus: "聚焦回答",
  reconstruct: "完整整理",
  reflective_access: "深度整理",
};

const elements = {
  authForm: document.querySelector("#auth-form"),
  authSubmit: document.querySelector("#auth-submit"),
  apiKey: document.querySelector("#api-key"),
  authStatus: document.querySelector("#auth-status"),
  authStateChip: document.querySelector("#auth-state-chip"),
  clearKey: document.querySelector("#clear-key"),
  connectionSummary: document.querySelector("#connection-summary"),
  catalogSummary: document.querySelector("#catalog-summary"),
  runtimeSummary: document.querySelector("#runtime-summary"),
  workflowSummary: document.querySelector("#workflow-summary"),
  reloadOverview: document.querySelector("#reload-overview"),
  loadGateDemo: document.querySelector("#load-gate-demo"),
  overviewGrid: document.querySelector("#overview-grid"),
  gateDemoResult: document.querySelector("#gate-demo-result"),
  workspaceTabs: [...document.querySelectorAll("[data-workspace-target]")],
  workspacePanels: [...document.querySelectorAll(".workspace-panel")],
  operationTabs: [...document.querySelectorAll("[data-operation-target]")],
  operationPanels: [...document.querySelectorAll("[data-operation-panel]")],
  ingestForm: document.querySelector("#ingest-form"),
  ingestSubmit: document.querySelector("#ingest-submit"),
  ingestContent: document.querySelector("#ingest-content"),
  ingestContentHelp: document.querySelector("#ingest-content-help"),
  ingestEpisodeId: document.querySelector("#ingest-episode-id"),
  ingestEpisodeHelp: document.querySelector("#ingest-episode-help"),
  ingestTimestampOrder: document.querySelector("#ingest-timestamp-order"),
  ingestOrderHelp: document.querySelector("#ingest-order-help"),
  ingestReset: document.querySelector("#ingest-reset"),
  ingestResult: document.querySelector("#ingest-result"),
  retrieveForm: document.querySelector("#retrieve-form"),
  retrieveSubmit: document.querySelector("#retrieve-submit"),
  retrieveQuery: document.querySelector("#retrieve-query"),
  retrieveEpisodeId: document.querySelector("#retrieve-episode-id"),
  retrieveMaxCandidates: document.querySelector("#retrieve-max-candidates"),
  retrieveReset: document.querySelector("#retrieve-reset"),
  retrieveResult: document.querySelector("#retrieve-result"),
  accessForm: document.querySelector("#access-form"),
  accessSubmit: document.querySelector("#access-submit"),
  accessQuery: document.querySelector("#access-query"),
  accessDepth: document.querySelector("#access-depth"),
  accessEpisodeId: document.querySelector("#access-episode-id"),
  accessTaskId: document.querySelector("#access-task-id"),
  accessExplain: document.querySelector("#access-explain"),
  accessReset: document.querySelector("#access-reset"),
  accessResult: document.querySelector("#access-result"),
  offlineForm: document.querySelector("#offline-form"),
  offlineSubmit: document.querySelector("#offline-submit"),
  offlineJobKind: document.querySelector("#offline-job-kind"),
  offlineEpisodeId: document.querySelector("#offline-episode-id"),
  offlineFocus: document.querySelector("#offline-focus"),
  offlineTargetRefs: document.querySelector("#offline-target-refs"),
  offlineReason: document.querySelector("#offline-reason"),
  offlinePriority: document.querySelector("#offline-priority"),
  offlineModeNote: document.querySelector("#offline-mode-note"),
  offlineReset: document.querySelector("#offline-reset"),
  offlineResult: document.querySelector("#offline-result"),
  settingsForm: document.querySelector("#settings-form"),
  settingsPreview: document.querySelector("#settings-preview"),
  settingsBackend: document.querySelector("#settings-backend"),
  settingsProfile: document.querySelector("#settings-profile"),
  settingsProvider: document.querySelector("#settings-provider"),
  settingsModel: document.querySelector("#settings-model"),
  settingsDevMode: document.querySelector("#settings-dev-mode"),
  settingsApply: document.querySelector("#settings-apply"),
  settingsRestore: document.querySelector("#settings-restore"),
  settingsReset: document.querySelector("#settings-reset"),
  settingsResult: document.querySelector("#settings-result"),
  debugForm: document.querySelector("#debug-form"),
  debugSubmit: document.querySelector("#debug-submit"),
  debugRunId: document.querySelector("#debug-run-id"),
  debugOperationId: document.querySelector("#debug-operation-id"),
  debugObjectId: document.querySelector("#debug-object-id"),
  debugLimit: document.querySelector("#debug-limit"),
  debugGuardStatus: document.querySelector("#debug-guard-status"),
  debugReset: document.querySelector("#debug-reset"),
  debugResult: document.querySelector("#debug-result"),
  authRequiredPanels: [...document.querySelectorAll("[data-auth-required]")],
  devRequiredPanels: [...document.querySelectorAll("[data-dev-required]")],
};

const state = {
  apiKey: window.localStorage.getItem(STORAGE_KEY) || "",
  catalogPage: null,
  gateDemoPage: null,
  settingsPage: null,
  ingestSubmissionHistory: loadStoredIngestHistory(),
  ingestHistoryPage: 1,
  ingestHistoryCursor: -1,
  ingestDraftSnapshot: "",
  busyActions: new Set(),
  activeWorkspace: DEFAULTS.workspace,
  activeOperation: DEFAULTS.operation,
};

function setStatus(message) {
  elements.authStatus.textContent = message;
}

function delay(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function isPositiveInteger(value) {
  const parsed = Number.parseInt(String(value), 10);
  return Number.isInteger(parsed) && parsed > 0;
}

function getOfflineTargetRefs() {
  return elements.offlineTargetRefs.value
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

function hasSettingsDraftSelection() {
  return Boolean(
    elements.settingsBackend.value
    || elements.settingsProfile.value
    || elements.settingsProvider.value
    || elements.settingsModel.value.trim()
    || elements.settingsDevMode.value,
  );
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

function setButtonRuleDisabled(button, disabled) {
  if (!button) {
    return;
  }
  button.dataset.ruleDisabled = disabled ? "true" : "false";
  applyButtonDisabledState(button);
}

function syncActionAvailability() {
  const offlineNeedsEpisode = elements.offlineJobKind.value === "reflect_episode";
  const offlineSubmitDisabled = offlineNeedsEpisode
    ? !elements.offlineEpisodeId.value.trim()
    : getOfflineTargetRefs().length < 2 || !elements.offlineReason.value.trim();

  setButtonRuleDisabled(elements.authSubmit, !elements.apiKey.value.trim());
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
  setButtonRuleDisabled(elements.settingsPreview, !hasSettingsDraftSelection());
  setButtonRuleDisabled(elements.settingsApply, !hasSettingsDraftSelection());
  setButtonRuleDisabled(
    elements.settingsRestore,
    !state.settingsPage?.snapshot_state?.previous_snapshot,
  );
  setButtonRuleDisabled(elements.debugSubmit, !hasDebugFilters());
}

function measureBusyButtonWidth(button, label) {
  const computed = window.getComputedStyle(button);
  const probe = document.createElement("span");
  const rootFontSize = Number.parseFloat(
    window.getComputedStyle(document.documentElement).fontSize,
  ) || 16;
  const gap = Number.parseFloat(computed.columnGap || computed.gap || "0");
  const padding =
    (Number.parseFloat(computed.paddingLeft) || 0)
    + (Number.parseFloat(computed.paddingRight) || 0)
    + (Number.parseFloat(computed.borderLeftWidth) || 0)
    + (Number.parseFloat(computed.borderRightWidth) || 0);

  probe.textContent = label;
  probe.style.position = "absolute";
  probe.style.visibility = "hidden";
  probe.style.whiteSpace = "nowrap";
  probe.style.font = computed.font;
  probe.style.fontWeight = computed.fontWeight;
  probe.style.letterSpacing = computed.letterSpacing;
  document.body.append(probe);
  const labelWidth = probe.getBoundingClientRect().width;
  probe.remove();

  return Math.ceil(labelWidth + padding + (rootFontSize * 0.85) + gap + 2);
}

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

function formatDateTime(value) {
  try {
    return new Date(value).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return String(value);
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatValue(value) {
  if (value === null || value === undefined) {
    return "暂无";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function renderMetricList(items) {
  return `
    <ul class="metric-list">
      ${items
        .map(
          ({ label, value }) => `
            <li>
              <span>${escapeHtml(label)}</span>
              <strong>${escapeHtml(formatValue(value))}</strong>
            </li>
          `,
        )
        .join("")}
    </ul>
  `;
}

function localizeViewport(value) {
  return VIEWPORT_LABELS[value] || value;
}

function localizeSettingKey(key) {
  return SETTING_LABELS[key] || key;
}

function localizeAccessDepth(value) {
  return ACCESS_DEPTH_LABELS[value] || value;
}

function localizeContentType(value) {
  return value || "未注明";
}

function localizeEntrypoint(entrypoint) {
  return ENTRYPOINT_LABELS[entrypoint] || {
    title: entrypoint,
    mode: "可用",
    summary: "这里显示一个已启用的功能入口。",
  };
}

function localizeGateEntry(entry) {
  return GATE_ENTRY_LABELS[entry.entry_id] || entry.title;
}

function renderOverviewEmpty(message) {
  elements.overviewGrid.innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
}

function renderGateDemoEmpty(message) {
  elements.gateDemoResult.innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
}

function renderSettingsSnapshot(snapshot, emptyMessage) {
  if (!snapshot) {
    return `<div class="empty-state">${escapeHtml(emptyMessage)}</div>`;
  }
  const changedKeys = (snapshot.changed_keys || []).map(localizeSettingKey).join("、") || "无";
  return `
    <ul class="notes-list">
      <li>记录编号：${escapeHtml(snapshot.snapshot_id)}</li>
      <li>操作类型：${escapeHtml(snapshot.action === "restore" ? "恢复" : "保存")}</li>
      <li>涉及项目：${escapeHtml(changedKeys)}</li>
    </ul>
  `;
}

function updateShellSignals() {
  const hasApiKey = Boolean(state.apiKey);
  const catalogEntries = state.catalogPage?.entries || [];
  const gateEntries = state.gateDemoPage?.entries || [];
  const runtime = state.settingsPage?.runtime || null;
  const devModeEnabled = Boolean(runtime?.dev_mode);

  elements.connectionSummary.textContent = hasApiKey
    ? "连接：已完成"
    : "连接：未完成";
  elements.catalogSummary.textContent = hasApiKey
    ? catalogEntries.length
      ? `功能：${catalogEntries.length} 个入口 / ${gateEntries.length} 条摘要`
      : "功能：等待同步"
    : "功能：未同步";
  elements.runtimeSummary.textContent = runtime
    ? `环境：${runtime.profile}`
    : "环境：未同步";
  elements.workflowSummary.textContent = !hasApiKey
    ? "状态：待连接"
    : devModeEnabled
      ? "状态：可排查"
      : "状态：可使用";
  elements.authStateChip.textContent = hasApiKey ? "已连接" : "未连接";
  elements.authStateChip.className = `status-chip ${hasApiKey ? "status-ok" : "status-warn"}`;
}

function renderOverview(catalog, settings) {
  const entries = catalog.entries || [];
  const snapshotState = settings.snapshot_state || {};
  const currentSnapshot = snapshotState.current_snapshot;
  const previousSnapshot = snapshotState.previous_snapshot;

  const entryCards = entries
    .map((entry) => {
      const meta = localizeEntrypoint(entry.entrypoint);
      return `
        <article class="overview-card">
          <div class="panel-kicker">${escapeHtml(meta.mode)}</div>
          <h3>${escapeHtml(meta.title)}</h3>
          <p class="meta">${escapeHtml(meta.summary)}</p>
          ${renderMetricList([
            {
              label: "适用设备",
              value: (entry.supported_viewports || []).map(localizeViewport).join(" / ") || "暂无",
            },
            { label: "示例数", value: (entry.scenario_ids || []).length },
            { label: "使用限制", value: entry.requires_dev_mode ? "需先开启高级排查" : "可直接使用" },
          ])}
        </article>
      `;
    })
    .join("");

  elements.overviewGrid.innerHTML = `
    <article class="overview-card">
      <div class="panel-kicker">当前环境</div>
      <h3>${escapeHtml(settings.runtime.profile)}</h3>
      <p class="meta">这里显示当前使用的环境、回答方式和排查状态。</p>
      ${renderMetricList([
        { label: "存储方式", value: settings.runtime.backend },
        { label: "回答方式", value: settings.provider.provider },
        { label: "当前模型", value: settings.provider.model },
        { label: "高级排查", value: settings.runtime.dev_mode ? "已开启" : "未开启" },
      ])}
    </article>
    <article class="overview-card">
      <div class="panel-kicker">设置记录</div>
      <h3>最近保存情况</h3>
      <p class="meta">保存设置后，系统会留下最近一次和上一次的记录，方便恢复。</p>
      ${renderMetricList([
        { label: "当前记录", value: currentSnapshot?.snapshot_id || "暂无" },
        { label: "上一次记录", value: previousSnapshot?.snapshot_id || "暂无" },
        { label: "摘要版本", value: catalog.bench_version || "暂无" },
      ])}
    </article>
    <article class="overview-card">
      <div class="panel-kicker">常用功能</div>
      <h3>${entries.length} 个入口已准备好</h3>
      <p class="meta">这里列出当前页面已经准备好的主要功能入口。</p>
      <ul class="pill-row">
        ${entries.map((entry) => `<li>${escapeHtml(localizeEntrypoint(entry.entrypoint).title)}</li>`).join("")}
      </ul>
    </article>
    ${entryCards || '<div class="empty-state">当前还没有可显示的功能入口。</div>'}
  `;
}

function renderSettingsOptions(settings) {
  fillSelect(elements.settingsBackend, settings.options.backends);
  fillSelect(elements.settingsProfile, settings.options.profiles);
  fillSelect(elements.settingsProvider, settings.options.provider_families);
  elements.settingsModel.placeholder = settings.provider.model;
}

function renderSettingsPage(settings) {
  const snapshotState = settings.snapshot_state || {};
  const currentSnapshot = snapshotState.current_snapshot;
  const previousSnapshot = snapshotState.previous_snapshot;
  elements.settingsResult.innerHTML = `
    <div class="status ${currentSnapshot ? "status-ok" : "status-warn"}">
      ${currentSnapshot ? "当前已有保存的设置记录" : "当前还没有保存过设置"}
    </div>
    <div class="result-grid">
      <div class="result-block">
        <h3>当前设置</h3>
        ${renderMetricList([
          { label: "存储方式", value: settings.runtime.backend },
          { label: "运行环境", value: settings.runtime.profile },
          { label: "回答方式", value: settings.provider.provider },
          { label: "模型名称", value: settings.provider.model },
          { label: "高级排查", value: settings.runtime.dev_mode ? "已开启" : "未开启" },
        ])}
      </div>
      <div class="result-block">
        <h3>当前记录</h3>
        ${renderSettingsSnapshot(currentSnapshot, "当前还没有已保存记录。")}
      </div>
      <div class="result-block">
        <h3>上一份记录</h3>
        ${renderSettingsSnapshot(previousSnapshot, "当前没有更早的记录可恢复。")}
      </div>
    </div>
  `;
}

function renderSettingsPreview(preview) {
  const changes = preview.changes || [];
  const envOverrides = Object.entries(preview.applied_env_overrides || {});
  elements.settingsResult.innerHTML = `
    <div class="status ${changes.length ? "status-ok" : "status-warn"}">
      ${changes.length ? `这次会调整 ${changes.length} 项设置` : "这次预览不会带来实际变化"}
    </div>
    <div class="result-grid">
      <div class="result-block">
        <h3>将要变化的项目</h3>
        <ul class="change-list">
          ${changes
            .map(
              (change) => `
                <li>
                  <strong>${escapeHtml(localizeSettingKey(change.key))}</strong>
                  <span>${escapeHtml(formatValue(change.before))} -> ${escapeHtml(formatValue(change.after))}</span>
                </li>
              `,
            )
            .join("") || "<li><span>当前设置与预览内容完全一致。</span></li>"}
        </ul>
      </div>
      <div class="result-block">
        <h3>补充说明</h3>
        <ul class="notes-list">
          <li>${envOverrides.length ? `系统还会同步调整 ${envOverrides.length} 项内部参数。` : "本次预览不需要额外补充项。"}</li>
        </ul>
      </div>
    </div>
  `;
}

function renderSettingsMutation(result) {
  const preview = result.preview || {};
  const currentSnapshot = result.current_snapshot;
  const previousSnapshot = result.previous_snapshot;
  const envOverrides = Object.entries(currentSnapshot?.applied_env_overrides || {});
  elements.settingsResult.innerHTML = `
    <div class="status status-ok">
      ${escapeHtml(result.action === "restore" ? "已恢复上一份设置" : "已保存当前设置")}
    </div>
    <div class="result-grid">
      <div class="result-block">
        <h3>当前记录</h3>
        ${renderSettingsSnapshot(currentSnapshot, "还没有当前记录。")}
      </div>
      <div class="result-block">
        <h3>上一份记录</h3>
        ${renderSettingsSnapshot(previousSnapshot, "当前没有更早的记录。")}
      </div>
      <div class="result-block">
        <h3>使用提示</h3>
        <ul class="notes-list">
          <li>${preview.restart_required ? "需要重启服务后，这次调整才会完全生效。" : "这次调整不需要重启，可直接生效。"}</li>
          <li>${envOverrides.length ? `系统还同步调整了 ${envOverrides.length} 项内部参数。` : "这次调整不需要额外补充项。"}</li>
        </ul>
      </div>
    </div>
  `;
}

function renderGateDemo(page) {
  const entries = page.entries || [];
  elements.gateDemoResult.innerHTML = `
    <div class="status ${entries.length ? "status-ok" : "status-warn"}">
      共整理出 ${entries.length} 条示例说明
    </div>
    <div class="result-grid">
      <div class="result-block">
        <h3>摘要列表</h3>
        <ul class="stack-list">
          ${entries
            .map(
              (entry) => `
                <li>
                  <div class="list-head">
                    <strong>${escapeHtml(localizeGateEntry(entry))}</strong>
                    <span class="mini-badge">${escapeHtml(GATE_KIND_LABELS[entry.kind] || entry.kind)}</span>
                  </div>
                  <div>${escapeHtml(entry.summary)}</div>
                  <div class="meta">
                    ${(entry.supported_viewports || []).map(localizeViewport).join(" / ") || "暂无"}
                    / ${(entry.scenario_ids || []).length} 个示例
                    / ${entry.requires_dev_mode ? "需先开启高级排查" : "可直接查看"}
                  </div>
                </li>
              `,
            )
            .join("") || "<li>当前还没有可显示的示例说明。</li>"}
        </ul>
      </div>
    </div>
  `;
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
  elements.accessResult.innerHTML = `
    <div class="status ${selectedObjects.length ? "status-ok" : "status-warn"}">
      本次回答参考了 ${escapeHtml(result.selected_count)} 条内容
    </div>
    <div class="result-grid">
      <div class="result-block">
        <h3>回答摘要</h3>
        <p class="meta">${escapeHtml(result.summary || "系统已整理好这次回答。")}</p>
        ${renderMetricList([
          { label: "参考范围", value: result.context_object_count },
          { label: "可参考内容", value: result.candidate_count },
          { label: "实际采用", value: result.selected_count },
          { label: "回答方式", value: localizeAccessDepth(result.resolved_depth) },
        ])}
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

function fillSelect(select, values) {
  const current = select.value;
  select.innerHTML = ['<option value="">保持不变</option>']
    .concat(
      (values || []).map(
        (value) =>
          `<option value="${escapeHtml(value)}"${value === current ? " selected" : ""}>${escapeHtml(value)}</option>`,
      ),
    )
    .join("");
}

function setActiveWorkspace(targetId) {
  state.activeWorkspace = targetId;
  elements.workspaceTabs.forEach((tab) => {
    const active = tab.dataset.workspaceTarget === targetId;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
  });
  elements.workspacePanels.forEach((panel) => {
    const active = panel.id === targetId;
    panel.classList.toggle("is-active", active);
    panel.setAttribute("aria-hidden", active ? "false" : "true");
  });
}

function setActiveOperation(targetId) {
  state.activeOperation = targetId;
  elements.operationTabs.forEach((tab) => {
    const active = tab.dataset.operationTarget === targetId;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
  });
  elements.operationPanels.forEach((panel) => {
    const active = panel.id === targetId;
    panel.classList.toggle("is-active", active);
    panel.setAttribute("aria-hidden", active ? "false" : "true");
  });
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
    : '<div class="empty-state">还没有设置变化预览。</div>';
  if (state.settingsPage) {
    renderSettingsPage(state.settingsPage);
  }
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
  renderOverviewEmpty("连接后可查看当前状态和可用功能。");
  renderGateDemoEmpty("连接后可查看示例说明。");
  resetIngestForm();
  resetRetrieveForm();
  resetAccessForm();
  resetOfflineForm();
  resetSettingsForm();
  resetDebugForm();
  updateShellSignals();
  syncPanelGuards();
  setActiveWorkspace(DEFAULTS.workspace);
  setActiveOperation(DEFAULTS.operation);
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

function collectSettingsPreviewRequest() {
  const body = {};
  if (elements.settingsBackend.value) {
    body.backend = elements.settingsBackend.value;
  }
  if (elements.settingsProfile.value) {
    body.profile = elements.settingsProfile.value;
  }
  if (elements.settingsProvider.value) {
    body.provider = elements.settingsProvider.value;
  }
  if (elements.settingsModel.value.trim()) {
    body.model = elements.settingsModel.value.trim();
  }
  if (elements.settingsDevMode.value) {
    body.dev_mode = elements.settingsDevMode.value === "true";
  }
  return body;
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
    renderOverviewEmpty("连接后可查看当前状态和可用功能。");
    resetSettingsForm();
    updateShellSignals();
    syncPanelGuards();
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
  updateShellSignals();
  syncPanelGuards();
}

async function refreshGateDemo() {
  if (!state.apiKey) {
    state.gateDemoPage = null;
    renderGateDemoEmpty("连接后可查看示例说明。");
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
    renderOverviewEmpty("连接后可查看当前状态和可用功能。");
    renderGateDemoEmpty("连接后可查看示例说明。");
    updateShellSignals();
    syncPanelGuards();
    return;
  }
  await Promise.all([refreshOverview(), refreshGateDemo()]);
}

function setButtonBusy(button, busyLabel) {
  if (!button) {
    return () => {};
  }

  const defaultLabel = button.dataset.defaultLabel || button.textContent.trim();
  const originalWidth = button.getBoundingClientRect().width;
  const busyWidth = measureBusyButtonWidth(button, busyLabel);
  button.dataset.defaultLabel = defaultLabel;
  button.dataset.busy = "true";
  button.classList.add("is-busy");
  applyButtonDisabledState(button);
  button.setAttribute("aria-busy", "true");
  button.textContent = busyLabel;
  button.style.minWidth = `${Math.ceil(Math.max(originalWidth, busyWidth))}px`;

  return () => {
    delete button.dataset.busy;
    button.classList.remove("is-busy");
    button.removeAttribute("aria-busy");
    button.textContent = defaultLabel;
    button.style.minWidth = "";
    applyButtonDisabledState(button);
  };
}

async function runUiAction(
  actionKey,
  {
    button = null,
    busyLabel = "处理中",
    minBusyMs = MIN_BUSY_MS.submit,
    work,
    readyMessage,
  },
) {
  if (state.busyActions.has(actionKey)) {
    return null;
  }

  state.busyActions.add(actionKey);
  const restoreButton = setButtonBusy(button, busyLabel);
  const startedAt = Date.now();

  try {
    setStatus(state.apiKey ? "正在处理中..." : "当前还没有连接。");
    const result = await work();
    await delay(Math.max(0, minBusyMs - (Date.now() - startedAt)));
    setStatus(readyMessage || (state.apiKey ? "可以继续操作。" : "当前还没有连接。"));
    return result;
  } catch (error) {
    await delay(Math.max(0, minBusyMs - (Date.now() - startedAt)));
    setStatus(error instanceof Error ? error.message : "页面暂时没有完成这次操作，请稍后重试。");
    return null;
  } finally {
    restoreButton();
    state.busyActions.delete(actionKey);
    syncActionAvailability();
  }
}

function bindClickAction(
  button,
  actionKey,
  {
    before = null,
    work,
    busyLabel,
    minBusyMs,
    readyMessage,
  },
) {
  button.addEventListener("click", () => {
    if (typeof before === "function") {
      before();
    }
    void runUiAction(actionKey, {
      button,
      busyLabel,
      minBusyMs,
      readyMessage,
      work,
    });
  });
}

function bindFormAction(
  form,
  actionKey,
  {
    button,
    before = null,
    work,
    busyLabel,
    minBusyMs,
    readyMessage,
  },
) {
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const submitter = event.submitter instanceof HTMLButtonElement ? event.submitter : button;
    if ((submitter || button)?.disabled) {
      return;
    }
    if (typeof before === "function") {
      before();
    }
    void runUiAction(actionKey, {
      button: submitter || button,
      busyLabel,
      minBusyMs,
      readyMessage,
      work,
    });
  });
}

elements.workspaceTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    setActiveWorkspace(tab.dataset.workspaceTarget || DEFAULTS.workspace);
  });
});

elements.operationTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    setActiveOperation(tab.dataset.operationTarget || DEFAULTS.operation);
  });
});

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
    setActiveWorkspace("workspace-operations");
    setActiveOperation("module-ingest");
  },
  busyLabel: "写入中",
  minBusyMs: MIN_BUSY_MS.submit,
  readyMessage: "写入完成，已保存到本地历史。",
  work: async () => {
    const request = collectIngestRequest();
    const result = await submitIngest(state.apiKey, request);
    rememberIngestSubmission(result, request);
    renderIngestHistory();
    applySuccessfulIngestState(result, request);
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
    setActiveWorkspace("workspace-operations");
    setActiveOperation("module-retrieve");
  },
  busyLabel: "检索中",
  minBusyMs: MIN_BUSY_MS.submit,
  work: async () => {
    const result = await submitRetrieve(state.apiKey, collectRetrieveRequest());
    renderRetrieveResult(result);
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
    setActiveWorkspace("workspace-operations");
    setActiveOperation("module-access");
  },
  busyLabel: "访问中",
  minBusyMs: MIN_BUSY_MS.submit,
  work: async () => {
    const result = await submitAccess(state.apiKey, collectAccessRequest());
    renderAccessResult(result);
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
    setActiveWorkspace("workspace-operations");
    setActiveOperation("module-offline");
  },
  busyLabel: "提交中",
  minBusyMs: MIN_BUSY_MS.submit,
  work: async () => {
    const result = await submitOffline(state.apiKey, collectOfflineRequest());
    renderOfflineResult(result);
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

bindFormAction(elements.settingsForm, "settings-preview", {
  button: elements.settingsPreview,
  before: () => {
    setActiveWorkspace("workspace-settings");
  },
  busyLabel: "预览中",
  minBusyMs: MIN_BUSY_MS.submit,
  work: async () => {
    const body = collectSettingsPreviewRequest();
    if (!Object.keys(body).length) {
      throw new Error("请至少选择一个设置项再预览");
    }
    const result = await previewSettings(state.apiKey, body);
    renderSettingsPreview(result);
  },
});

bindClickAction(elements.settingsApply, "settings-apply", {
  before: () => {
    setActiveWorkspace("workspace-settings");
  },
  busyLabel: "应用中",
  minBusyMs: MIN_BUSY_MS.mutate,
  work: async () => {
    const body = collectSettingsPreviewRequest();
    if (!Object.keys(body).length) {
      throw new Error("请至少选择一个设置项再应用");
    }
    const result = await applySettings(state.apiKey, body);
    const refreshedSettings = await loadSettings(state.apiKey);
    state.settingsPage = refreshedSettings;
    renderSettingsOptions(refreshedSettings);
    renderSettingsPage(refreshedSettings);
    if (state.catalogPage) {
      renderOverview(state.catalogPage, refreshedSettings);
    }
    renderSettingsMutation(result);
    updateShellSignals();
    syncPanelGuards();
  },
});

bindClickAction(elements.settingsRestore, "settings-restore", {
  before: () => {
    setActiveWorkspace("workspace-settings");
  },
  busyLabel: "恢复中",
  minBusyMs: MIN_BUSY_MS.mutate,
  work: async () => {
    const result = await restoreSettings(state.apiKey);
    const refreshedSettings = await loadSettings(state.apiKey);
    state.settingsPage = refreshedSettings;
    renderSettingsOptions(refreshedSettings);
    renderSettingsPage(refreshedSettings);
    if (state.catalogPage) {
      renderOverview(state.catalogPage, refreshedSettings);
    }
    renderSettingsMutation(result);
    updateShellSignals();
    syncPanelGuards();
  },
});

bindClickAction(elements.settingsReset, "settings-reset", {
  busyLabel: "重置中",
  minBusyMs: MIN_BUSY_MS.reset,
  work: async () => {
    resetSettingsForm();
  },
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
  elements.settingsBackend,
  elements.settingsProfile,
  elements.settingsProvider,
  elements.settingsModel,
  elements.settingsDevMode,
  elements.debugRunId,
  elements.debugOperationId,
  elements.debugObjectId,
  elements.debugLimit,
].forEach(bindAvailabilitySync);

// Mobile sidebar toggle
const mobToggle = document.querySelector("#mob-toggle");
const sidebarEl = document.querySelector("#sidebar");
const backdropEl = document.querySelector("#sidebar-backdrop");
function closeSidebar() {
  sidebarEl.classList.remove("is-open");
  backdropEl.classList.remove("is-open");
}
if (mobToggle) {
  mobToggle.addEventListener("click", () => {
    const open = sidebarEl.classList.toggle("is-open");
    backdropEl.classList.toggle("is-open", open);
  });
}
if (backdropEl) {
  backdropEl.addEventListener("click", closeSidebar);
}
// Close sidebar when workspace tab clicked on mobile
elements.workspaceTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    if (window.innerWidth <= 1024) closeSidebar();
  });
});

elements.apiKey.value = state.apiKey;
setActiveWorkspace(state.activeWorkspace);
setActiveOperation(state.activeOperation);
renderIngestHistory();
syncIngestFieldHints();
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
  renderOverviewEmpty("连接后可查看当前状态和可用功能。");
  renderGateDemoEmpty("连接后可查看示例说明。");
}
