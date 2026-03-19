const EMPTY_DEBUG_RESULT = '<div class="empty-state">还没有排查结果。</div>';

const DEBUG_SCOPE_LABELS = {
  primitive: "原语处理",
  retrieval: "召回检索",
  workspace: "工作区上下文",
  access: "访问问答",
  offline: "后台任务",
  governance: "治理流程",
  object_delta: "内容变化",
};

const DEBUG_EVENT_KIND_LABELS = {
  entry: "进入步骤",
  decision: "处理中决策",
  state_delta: "状态变化",
  context_result: "上下文结果",
  action_result: "执行结果",
};

function formatOptionLabel(option) {
  const label = option.label || option.value;
  if (!option.event_count) {
    return label;
  }
  return `${label} (${option.event_count})`;
}

function renderDatalistOptions(datalist, options) {
  if (!datalist) {
    return;
  }
  const fragment = document.createDocumentFragment();
  (options || []).forEach((option) => {
    const element = document.createElement("option");
    element.value = option.value;
    element.label = formatOptionLabel(option);
    fragment.append(element);
  });
  datalist.replaceChildren(fragment);
}

function renderSelectOptions(select, options, selectedValue, placeholderLabel) {
  const values = (options || []).map((option) => option.value);
  const effectiveValue = values.includes(selectedValue) ? selectedValue : "";
  const fragment = document.createDocumentFragment();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = placeholderLabel;
  placeholder.selected = !effectiveValue;
  fragment.append(placeholder);
  (options || []).forEach((option) => {
    const element = document.createElement("option");
    element.value = option.value;
    element.textContent = option.label;
    element.selected = option.value === effectiveValue;
    fragment.append(element);
  });
  select.replaceChildren(fragment);
}

function resolveExistingValue(currentValue, fallbackValue = "") {
  const trimmed = String(currentValue || "").trim();
  if (trimmed) {
    return trimmed;
  }
  return fallbackValue;
}

function parseDatetimeLocal(rawValue) {
  const value = String(rawValue || "").trim();
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    throw new Error("时间范围格式无效，请重新选择开始或结束时间。");
  }
  return parsed.toISOString();
}

function buildQuerySummary(query, workspace, formatDateTime, escapeHtml) {
  const filters = [];
  if (query.run_id) {
    filters.push(`请求：${escapeHtml(query.run_id)}`);
  }
  if (query.operation_id) {
    filters.push(`操作：${escapeHtml(query.operation_id)}`);
  }
  if (query.object_id) {
    filters.push(`内容：${escapeHtml(query.object_id)}`);
  }
  if (query.job_id) {
    filters.push(`任务：${escapeHtml(query.job_id)}`);
  }
  if (query.workspace_id) {
    filters.push(`工作区：${escapeHtml(query.workspace_id)}`);
  }
  if (query.scopes?.length) {
    filters.push(
      `范围：${escapeHtml(
        query.scopes.map((value) => DEBUG_SCOPE_LABELS[value] || value).join(" / "),
      )}`,
    );
  }
  if (query.event_kinds?.length) {
    filters.push(
      `步骤：${escapeHtml(
        query.event_kinds.map((value) => DEBUG_EVENT_KIND_LABELS[value] || value).join(" / "),
      )}`,
    );
  }
  if (query.occurred_after || query.occurred_before) {
    const windowLabel = [
      query.occurred_after ? formatDateTime(query.occurred_after) : "起点不限",
      query.occurred_before ? formatDateTime(query.occurred_before) : "终点不限",
    ].join(" ~ ");
    filters.push(`时间：${escapeHtml(windowLabel)}`);
  } else if (workspace?.earliest_occurred_at || workspace?.latest_occurred_at) {
    filters.push(
      `可查范围：${escapeHtml(
        [
          workspace.earliest_occurred_at ? formatDateTime(workspace.earliest_occurred_at) : "未知起点",
          workspace.latest_occurred_at ? formatDateTime(workspace.latest_occurred_at) : "未知终点",
        ].join(" ~ "),
      )}`,
    );
  }
  return filters.length
    ? `<ul class="pill-row">${filters.map((item) => `<li>${item}</li>`).join("")}</ul>`
    : '<p class="meta">当前没有额外筛选，会按默认条件读取最近一组处理记录。</p>';
}

function buildDeltaFieldSummary(delta) {
  const keys = Object.keys(delta.delta || {});
  return keys.length ? keys.join(", ") : "本次记录没有可展开的变化字段。";
}

export function createDebugFeature({
  state,
  elements,
  bindClickAction,
  bindFormAction,
  busyTimes,
  defaultLimit,
  setActiveWorkspace,
  loadDebugTimelineWorkspace,
  loadDebugTimeline,
  syncActionAvailability,
  escapeHtml,
  formatDateTime,
}) {
  let workspace = null;

  function hasFilters() {
    return Boolean(
      elements.debugRunId.value.trim()
      || elements.debugOperationId.value.trim()
      || elements.debugObjectId.value.trim()
      || elements.debugJobId.value.trim()
      || elements.debugWorkspaceId.value.trim()
      || elements.debugScope.value
      || elements.debugEventKind.value
      || elements.debugOccurredAfter.value
      || elements.debugOccurredBefore.value,
    );
  }

  function renderFilterSummary(message) {
    if (!elements.debugFilterSummary) {
      return;
    }
    elements.debugFilterSummary.textContent = message;
  }

  function renderWorkspace(nextWorkspace) {
    workspace = nextWorkspace;
    renderDatalistOptions(elements.debugRunOptions, workspace?.run_options || []);
    renderDatalistOptions(elements.debugOperationOptions, workspace?.operation_options || []);
    renderDatalistOptions(elements.debugObjectOptions, workspace?.object_options || []);
    renderDatalistOptions(elements.debugJobOptions, workspace?.job_options || []);
    renderDatalistOptions(elements.debugWorkspaceOptions, workspace?.workspace_options || []);

    renderSelectOptions(
      elements.debugScope,
      (workspace?.scope_options || []).map((option) => ({
        ...option,
        label: DEBUG_SCOPE_LABELS[option.value] || option.label || option.value,
      })),
      elements.debugScope.value,
      "全部范围",
    );
    renderSelectOptions(
      elements.debugEventKind,
      (workspace?.event_kind_options || []).map((option) => ({
        ...option,
        label: DEBUG_EVENT_KIND_LABELS[option.value] || option.label || option.value,
      })),
      elements.debugEventKind.value,
      "全部类型",
    );

    elements.debugRunId.value = resolveExistingValue(
      elements.debugRunId.value,
      workspace?.default_run_id || "",
    );
    renderFilterSummary(
      workspace?.total_event_count
        ? `已载入 ${workspace.total_event_count} 条处理记录，可按请求、操作、内容、任务、工作区、范围、步骤类型和时间范围筛选。`
        : "当前还没有可筛选的处理记录，先执行一次写入、检索、问答或后台任务后再回来查看。",
    );
    syncActionAvailability();
  }

  function clearWorkspace() {
    workspace = null;
    elements.debugRunId.value = "";
    elements.debugOperationId.value = "";
    elements.debugObjectId.value = "";
    elements.debugJobId.value = "";
    elements.debugWorkspaceId.value = "";
    elements.debugScope.value = "";
    elements.debugEventKind.value = "";
    elements.debugOccurredAfter.value = "";
    elements.debugOccurredBefore.value = "";
    elements.debugLimit.value = String(defaultLimit);
    renderDatalistOptions(elements.debugRunOptions, []);
    renderDatalistOptions(elements.debugOperationOptions, []);
    renderDatalistOptions(elements.debugObjectOptions, []);
    renderDatalistOptions(elements.debugJobOptions, []);
    renderDatalistOptions(elements.debugWorkspaceOptions, []);
    renderSelectOptions(elements.debugScope, [], "", "连接后加载");
    renderSelectOptions(elements.debugEventKind, [], "", "连接后加载");
    renderFilterSummary("连接后会自动加载最近请求、可搜索编号和可用时间范围。");
    elements.debugResult.innerHTML = EMPTY_DEBUG_RESULT;
    syncActionAvailability();
  }

  function resetForm() {
    elements.debugRunId.value = workspace?.default_run_id || "";
    elements.debugOperationId.value = "";
    elements.debugObjectId.value = "";
    elements.debugJobId.value = "";
    elements.debugWorkspaceId.value = "";
    elements.debugScope.value = "";
    elements.debugEventKind.value = "";
    elements.debugOccurredAfter.value = "";
    elements.debugOccurredBefore.value = "";
    elements.debugLimit.value = String(defaultLimit);
    elements.debugResult.innerHTML = EMPTY_DEBUG_RESULT;
    syncActionAvailability();
  }

  function collectRequest() {
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
    if (elements.debugJobId.value.trim()) {
      body.job_id = elements.debugJobId.value.trim();
    }
    if (elements.debugWorkspaceId.value.trim()) {
      body.workspace_id = elements.debugWorkspaceId.value.trim();
    }
    if (elements.debugScope.value) {
      body.scopes = [elements.debugScope.value];
    }
    if (elements.debugEventKind.value) {
      body.event_kinds = [elements.debugEventKind.value];
    }
    const occurredAfter = parseDatetimeLocal(elements.debugOccurredAfter.value);
    const occurredBefore = parseDatetimeLocal(elements.debugOccurredBefore.value);
    if (occurredAfter) {
      body.occurred_after = occurredAfter;
    }
    if (occurredBefore) {
      body.occurred_before = occurredBefore;
    }
    return body;
  }

  function renderTimelineResult(result) {
    const timeline = result.timeline || [];
    const deltas = result.object_deltas || [];
    const contextViews = result.context_views || [];
    const evidenceViews = result.evidence_views || [];
    const querySummary = buildQuerySummary(result.query || {}, workspace, formatDateTime, escapeHtml);
    const statusLabel = result.matched_event_count > timeline.length
      ? `共匹配 ${result.matched_event_count} 条处理记录，当前展示前 ${timeline.length} 条。`
      : `共找到 ${timeline.length} 条处理记录。`;
    elements.debugResult.innerHTML = `
      <div class="status ${timeline.length ? "status-ok" : "status-warn"}">
        ${statusLabel}
      </div>
      <div class="result-panel">
        <h3>本次筛选</h3>
        ${querySummary}
      </div>
      <div class="timeline-list">
        ${timeline
          .map(
            (event) => `
              <article class="event-card">
                <h3>${escapeHtml(event.label)}</h3>
                <p class="meta">范围：${escapeHtml(DEBUG_SCOPE_LABELS[event.scope] || event.scope)} / 类型：${escapeHtml(DEBUG_EVENT_KIND_LABELS[event.kind] || event.kind)}</p>
                <p>${escapeHtml(event.summary)}</p>
                <p class="meta">请求：${escapeHtml(event.run_id)} / 操作：${escapeHtml(event.operation_id)}</p>
                <p class="meta">${escapeHtml(formatDateTime(event.occurred_at))}</p>
              </article>
            `,
          )
          .join("") || '<div class="empty-state">这次没有找到相关处理记录。</div>'}
      </div>
      <div class="result-panel">
        <h3>内容变化</h3>
        <ul class="stack-list">
          ${deltas
            .map(
              (delta) => `
                <li>
                  <strong>内容编号：${escapeHtml(delta.object_id)}</strong>
                  <div class="meta">第 ${escapeHtml(delta.object_version)} 版 / ${escapeHtml(formatDateTime(delta.occurred_at))}</div>
                  <div>${escapeHtml(delta.summary)}</div>
                  <div class="meta">变化字段：${escapeHtml(buildDeltaFieldSummary(delta))}</div>
                </li>
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
                  <div class="meta">内容类型：${escapeHtml(view.object_type || "未知")} / ${view.selected ? "已用于本次结果" : "作为备选参考"}</div>
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

  async function refreshWorkspace() {
    if (!state.apiKey) {
      clearWorkspace();
      return null;
    }
    const nextWorkspace = await loadDebugTimelineWorkspace(state.apiKey);
    renderWorkspace(nextWorkspace);
    return nextWorkspace;
  }

  bindFormAction(elements.debugForm, "debug-submit", {
    button: elements.debugSubmit,
    before: () => {
      setActiveWorkspace("workspace-debug");
    },
    busyLabel: "加载中",
    minBusyMs: busyTimes.submit,
    work: async () => {
      const body = collectRequest();
      if (!hasFilters()) {
        throw new Error("请至少填写一个筛选条件，或先刷新筛选项后直接查看最近请求。");
      }
      const result = await loadDebugTimeline(state.apiKey, body);
      renderTimelineResult(result);
    },
  });

  bindClickAction(elements.debugRefreshWorkspace, "debug-refresh-workspace", {
    before: () => {
      setActiveWorkspace("workspace-debug");
    },
    busyLabel: "刷新中",
    minBusyMs: busyTimes.refresh,
    readyMessage: "筛选项已更新。",
    work: refreshWorkspace,
  });

  bindClickAction(elements.debugReset, "debug-reset", {
    busyLabel: "重置中",
    minBusyMs: busyTimes.reset,
    work: async () => {
      resetForm();
    },
  });

  return {
    clearWorkspace,
    collectRequest,
    hasFilters,
    refreshWorkspace,
    renderTimelineResult,
    resetForm,
  };
}
