export function createOverviewFeature({
  documentRef,
  elements,
  navigate,
  state,
  getAnswerModeFromSettings,
  getLlmActiveService,
  localizeAnswerMode,
  localizeEntrypoint,
  localizeProviderFamily,
  localizeGateEntry,
  GATE_KIND_LABELS,
  escapeHtml,
}) {
  function getUserFacingCatalogEntries(catalog) {
    return (catalog?.entries || []).filter((entry) => entry.entrypoint !== "gate_demo");
  }

  function getOverviewEntrypointTarget(entrypoint) {
    const operationTargets = {
      ingest: "module-ingest",
      retrieve: "module-retrieve",
      access: "module-access",
      offline: "module-offline",
      benchmark: "module-benchmark",
    };
    if (operationTargets[entrypoint]) {
      return { workspace: "workspace-operations", panel: operationTargets[entrypoint] };
    }
    if (entrypoint === "gate_demo") {
      return { workspace: "workspace-overview", panel: "gate-demo-panel" };
    }
    return null;
  }

  function jumpToOverviewEntrypoint(entrypoint) {
    const target = getOverviewEntrypointTarget(entrypoint);
    if (!target) {
      return;
    }
    navigate({
      activeWorkspace: target.workspace,
      activeOperation: target.workspace === "workspace-operations" && target.panel
        ? target.panel
        : state.activeOperation,
    });
    if (entrypoint === "gate_demo") {
      documentRef.querySelector("#overview-notes")?.setAttribute("open", "open");
      elements.loadGateDemo?.focus();
    }
  }

  function renderOverviewEmpty(message) {
    elements.overviewGrid.innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
  }

  function renderGateDemoEmpty(message) {
    elements.gateDemoResult.innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
  }

  function renderOverview(catalog, settings) {
    const entries = getUserFacingCatalogEntries(catalog);
    const answerMode = getAnswerModeFromSettings(settings);
    const activeService = getLlmActiveService(settings);
    const currentService = answerMode === "llm"
      ? `${activeService?.name || localizeProviderFamily(settings.provider.provider_family)} / ${settings.provider.model}`
      : "内建模式";
    const guidance = answerMode === "llm"
      ? "当前已经启用 LLM，适合直接进行访问问答。"
      : "当前使用内建模式；需要更自然的回答时，可到配置里启用 LLM。";
    const orderedEntries = ["ingest", "retrieve", "access", "offline", "benchmark"]
      .map((entrypoint) => entries.find((entry) => entry.entrypoint === entrypoint))
      .filter(Boolean);

    const entryRows = orderedEntries
      .map((entry) => {
        const meta = localizeEntrypoint(entry.entrypoint);
        return `
          <button type="button"
                  class="overview-entry-row"
                  data-overview-entrypoint="${escapeHtml(entry.entrypoint)}">
            <span class="overview-entry-mode">${escapeHtml(meta.mode)}</span>
            <span class="overview-entry-copy">
              <strong>${escapeHtml(meta.title)}</strong>
              <span>${escapeHtml(meta.summary)}</span>
              ${entry.requires_dev_mode ? '<em class="overview-entry-note">需先开启高级排查</em>' : ""}
            </span>
            <span class="overview-entry-action">前往</span>
          </button>
        `;
      })
      .join("");

    elements.overviewGrid.innerHTML = `
      <section class="overview-stage">
        <section class="overview-hero">
          <div class="overview-hero-main">
            <div class="panel-kicker">当前状态</div>
            <h2>工作台已连接</h2>
            <p>${escapeHtml(guidance)}</p>
            <div class="overview-status-tags">
              <span>${escapeHtml(settings.runtime.profile)}</span>
              <span>${escapeHtml(localizeAnswerMode(answerMode))}</span>
              <span>${escapeHtml(settings.runtime.dev_mode ? "高级排查已开启" : "高级排查已关闭")}</span>
            </div>
          </div>
          <dl class="overview-runtime-list">
            <div class="overview-runtime-item">
              <dt>当前服务</dt>
              <dd>${escapeHtml(currentService)}</dd>
            </div>
            <div class="overview-runtime-item">
              <dt>下一步</dt>
              <dd>先写入，再查找；要验证整条记忆生命周期时进入生命周期基准。</dd>
            </div>
          </dl>
        </section>

        <section class="overview-flow">
          <div class="overview-flow-copy">
            <div class="panel-kicker">使用路径</div>
            <h3>按这个顺序开始</h3>
            <p>总览不再解释内部元数据，只保留你真正会用到的工作路径。</p>
          </div>
          <ol class="overview-flow-steps">
            <li><strong>1. 写入记忆</strong><span>先把事实、偏好和结论保存进去。</span></li>
            <li><strong>2. 召回检索</strong><span>确认系统里是否已经有相关内容。</span></li>
            <li><strong>3. 访问问答</strong><span>把已保存内容整理成回答。</span></li>
            <li><strong>4. 后台任务</strong><span>把需要慢慢处理的整理任务交给系统。</span></li>
            <li><strong>5. 生命周期基准</strong><span>对真实维护链路跑阶段指标并保存可回查报告。</span></li>
          </ol>
        </section>

        <section class="overview-entry-list">
          <div class="overview-entry-list-head">
            <div>
              <div class="panel-kicker">主要入口</div>
              <h3>直接进入操作区</h3>
            </div>
            <span class="overview-entry-count">${escapeHtml(`${orderedEntries.length} 个常用入口`)}</span>
          </div>
          <div class="overview-entry-rows">
            ${entryRows || '<div class="empty-state">当前还没有可显示的功能入口。</div>'}
          </div>
        </section>
      </section>
    `;
  }

  function renderGateDemo(page) {
    const entries = page.entries || [];
    const visibleEntries = entries.slice(0, 3);
    elements.gateDemoResult.innerHTML = `
      ${
        visibleEntries.length
          ? `
            <p class="meta overview-note-intro">最近同步到 ${visibleEntries.length} 条补充信息。</p>
            <div class="overview-note-list">
              ${visibleEntries
                .map(
                  (entry) => `
                    <article class="overview-note-item">
                      <div class="list-head">
                        <strong>${escapeHtml(localizeGateEntry(entry))}</strong>
                        <span class="mini-badge">${escapeHtml(GATE_KIND_LABELS[entry.kind] || entry.kind)}</span>
                      </div>
                      <p class="meta">${escapeHtml(entry.summary)}</p>
                    </article>
                  `,
                )
                .join("")}
            </div>
            ${
              entries.length > visibleEntries.length
                ? `<p class="meta overview-note-foot">其余 ${entries.length - visibleEntries.length} 条内容已收起。</p>`
                : ""
            }
          `
          : '<div class="empty-state">当前还没有可显示的补充说明。</div>'
      }
    `;
  }

  return {
    getUserFacingCatalogEntries,
    getOverviewEntrypointTarget,
    jumpToOverviewEntrypoint,
    renderOverviewEmpty,
    renderGateDemoEmpty,
    renderOverview,
    renderGateDemo,
  };
}
