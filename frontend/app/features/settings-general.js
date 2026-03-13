export function createSettingsGeneralFeature({
  elements,
  getAnswerModeFromSettings,
  getLlmActiveService,
  localizeAnswerMode,
  localizeProviderFamily,
  localizeSettingKey,
  formatValue,
  renderMetricList,
  escapeHtml,
}) {
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

  function renderSettingsOptions(settings) {
    elements.settingsProfile.value = settings.runtime.profile;
    elements.settingsProvider.value = getAnswerModeFromSettings(settings);
    elements.settingsDevMode.checked = Boolean(settings.runtime.dev_mode);
  }

  function renderSettingsPage(settings, statusMessage = "修改后会立即生效。", statusKind = "status-ok") {
    const answerMode = getAnswerModeFromSettings(settings);
    const activeService = getLlmActiveService(settings);
    elements.settingsResult.innerHTML = `
      <div class="status ${escapeHtml(statusKind)}">
        ${escapeHtml(statusMessage)}
      </div>
      ${renderMetricList([
        { label: "运行环境", value: `${settings.runtime.profile}（只读）` },
        { label: "回答方式", value: localizeAnswerMode(answerMode) },
        {
          label: "LLM 细节",
          value: answerMode === "llm"
            ? `${activeService?.name || localizeProviderFamily(settings.provider.provider_family)} / ${settings.provider.model}`
            : "当前使用内建模式",
        },
        { label: "高级排查", value: settings.runtime.dev_mode ? "已开启" : "已关闭" },
      ])}
      <div class="meta">
        ${escapeHtml(
          answerMode === "llm"
            ? (
              settings.provider.auth_configured
                ? "当前 LLM 可直接使用。"
                : "当前 LLM 还缺少可用鉴权。"
            )
            : "需要切换服务或模型时，可在右侧的 LLM 服务里继续设置。",
        )}
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

  function renderSettingsMutation(result, currentSettings) {
    const action = result?.action === "restore" ? "已恢复并立即生效。" : "设置已立即生效。";
    renderSettingsPage(currentSettings, action, "status-ok");
  }

  return {
    renderSettingsSnapshot,
    renderSettingsOptions,
    renderSettingsPage,
    renderSettingsPreview,
    renderSettingsMutation,
  };
}
