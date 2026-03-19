import { OPERATION_CHAIN_CONFIG } from "./constants.js";
import {
  escapeHtml,
  formatDateTime,
  formatValue,
  localizeAccessDepth,
  localizeAnswerMode,
  localizeOfflineJobKind,
  localizeOperationChainStatus,
  localizeOperationStepStatus,
  localizeProviderFamily,
  truncateText,
} from "./utils.js";

export function createOperationChainManager({
  elements,
  state,
  defaults,
  getAnswerModeFromSettings,
  getLlmActiveService,
  syncModalOpenState,
}) {
  let operationChainFocusTimer = 0;

  function compactChainDetails(items) {
    return (items || [])
      .filter((item) => item && item.label)
      .map(({ label, value }) => ({
        label,
        value: Array.isArray(value)
          ? (value.length ? value.join(", ") : "无")
          : formatValue(value),
      }))
      .filter((item) => item.value !== "暂无" || item.label.includes("trace") || item.label.includes("任务编号"));
  }

  function llmTraceModalDetail(summary = "查看本轮完整请求与回答") {
    return {
      label: "详细项",
      kind: "trace-modal",
      summary,
    };
  }

  function createOperationChainStep(step, overrides = {}) {
    return {
      id: step.id,
      label: step.label,
      summary: step.summary,
      status: "upcoming",
      details: [],
      highlighted: Boolean(step.highlighted),
      defaultOpen: false,
      ...overrides,
    };
  }

  function isOperationDrawerViewport() {
    return window.innerWidth <= 1024;
  }

  function getOperationChainConfig(operationId) {
    return OPERATION_CHAIN_CONFIG[operationId] || OPERATION_CHAIN_CONFIG[defaults.operation];
  }

  function isBenchmarkReportReload(request) {
    return !request?.dataset_name && !request?.source_path;
  }

  function getLatestBenchmarkStage(result) {
    const stages = result?.stage_reports || [];
    return stages[stages.length - 1] || null;
  }

  function buildOperationRuntimeContext() {
    const settings = state.settingsPage;
    const answerMode = getAnswerModeFromSettings(settings);
    const activeService = getLlmActiveService(settings);
    const provider = settings?.provider || {};
    return {
      profile: settings?.runtime?.profile || "未同步",
      answerMode,
      serviceName: answerMode === "llm"
        ? (activeService?.name || localizeProviderFamily(provider.provider_family))
        : "内建模式",
      providerFamily: provider.provider_family || "deterministic",
      model: provider.model || (answerMode === "builtin" ? "deterministic" : "未注明"),
      endpoint: provider.endpoint || activeService?.endpoint || null,
      devMode: Boolean(settings?.runtime?.dev_mode),
    };
  }

  function buildOperationChainRuntimeFields(runtimeContext) {
    return compactChainDetails([
      { label: "运行环境", value: runtimeContext.profile },
      { label: "当前模式", value: localizeAnswerMode(runtimeContext.answerMode) },
      { label: "当前服务", value: runtimeContext.serviceName },
      { label: "协议", value: localizeProviderFamily(runtimeContext.providerFamily) },
      { label: "模型", value: runtimeContext.model },
      { label: "服务地址", value: runtimeContext.endpoint || "当前未使用外部 LLM" },
      { label: "高级排查", value: runtimeContext.devMode ? "已开启" : "未开启" },
    ]);
  }

  function buildOperationChainSnapshot(operationId, payload) {
    const config = getOperationChainConfig(operationId);
    return {
      operationId,
      title: config.title,
      status: payload.status,
      submittedAt: payload.submittedAt || null,
      requestSummary: payload.requestSummary || [],
      runtimeContext: payload.runtimeContext || buildOperationRuntimeContext(),
      steps: payload.steps || [],
      resultSummary: payload.resultSummary || config.idleSummary,
      errorMessage: payload.errorMessage || null,
      llmTracePayload: payload.llmTracePayload || null,
    };
  }

  function buildLlmTraceExchanges(answerTrace, answerText) {
    const rawExchanges = Array.isArray(answerTrace?.exchanges) ? answerTrace.exchanges : [];
    const exchanges = rawExchanges
      .map((exchange, index) => ({
        order: Number.isInteger(exchange?.order) ? exchange.order : index + 1,
        requestText: String(exchange?.request_text || "").trim(),
        responseText: String(exchange?.response_text || "").trim(),
      }))
      .filter((exchange) => exchange.requestText || exchange.responseText)
      .sort((left, right) => left.order - right.order);

    if (exchanges.length) {
      return exchanges;
    }

    const requestText = String(answerTrace?.request_text || "").trim();
    const responseText = String(answerTrace?.response_text || answerText || "").trim();
    if (!requestText && !responseText) {
      return [];
    }
    return [{ order: 1, requestText, responseText }];
  }

  function buildLlmTraceModalPayload({ request, result, runtimeContext, submittedAt }) {
    const answer = result.answer || null;
    const answerTrace = answer?.trace || null;
    const providerFamily = answerTrace?.provider_family || runtimeContext.providerFamily;
    const exchanges = buildLlmTraceExchanges(answerTrace, answer?.text || result.summary || "");
    if (!answerTrace && !exchanges.length) {
      return null;
    }

    return {
      title: "LLM 调用详情",
      caption: "这里展示本轮提交，以及发送给 AI 和 AI 返回的完整内容。",
      status: Boolean(answerTrace?.fallback_used) ? "fallback" : "success",
      submittedAt,
      modeLabel: Boolean(answerTrace?.fallback_used) ? "本轮已回退" : "本轮详情",
      submissionFields: compactChainDetails([
        { label: "问题", value: request.query },
        { label: "回答方式", value: localizeAccessDepth(result.resolved_depth || request.depth) },
        { label: "记录分组", value: request.episode_id || "全部分组" },
        { label: "任务编号", value: request.task_id || "未关联" },
        { label: "采用内容数量", value: result.selected_count },
        { label: "上下文对象数量", value: result.context_object_count },
      ]),
      llmFields: compactChainDetails([
        { label: "服务名", value: runtimeContext.serviceName },
        { label: "协议", value: localizeProviderFamily(providerFamily) },
        { label: "模型", value: runtimeContext.model },
        { label: "服务地址", value: answerTrace?.endpoint || runtimeContext.endpoint || "未返回" },
        { label: "是否回退", value: answerTrace?.fallback_used ? "是" : "否" },
        { label: "回退原因", value: answerTrace?.fallback_reason || "无" },
      ]),
      finalAnswerText: String(answer?.text || result.summary || "").trim(),
      exchanges,
    };
  }

  function renderLlmTraceSummaryFields(items) {
    return `
      <dl class="llm-trace-summary-grid">
        ${items
          .map(
            (item) => `
              <div class="llm-trace-summary-item">
                <dt>${escapeHtml(item.label)}</dt>
                <dd>${escapeHtml(item.value)}</dd>
              </div>
            `,
          )
          .join("")}
      </dl>
    `;
  }

  function renderLlmTraceExchange(exchange) {
    const requestText = exchange.requestText || "本轮没有记录发送给 AI 的原文。";
    const responseText = exchange.responseText || "本轮没有记录 AI 的原始返回。";
    return `
      <article class="llm-trace-exchange">
        <div class="llm-trace-exchange-head">
          <strong>第 ${escapeHtml(exchange.order)} 轮</strong>
          <span>${escapeHtml(
            exchange.requestText && exchange.responseText
              ? "包含完整请求与回答"
              : (exchange.requestText ? "仅记录请求" : "仅记录回答"),
          )}</span>
        </div>
        <div class="llm-trace-exchange-grid">
          <section class="llm-trace-message-block">
            <div class="llm-trace-message-head">
              <h4>发送给 AI 的原文</h4>
            </div>
            <pre class="llm-trace-raw">${escapeHtml(requestText)}</pre>
          </section>
          <section class="llm-trace-message-block">
            <div class="llm-trace-message-head">
              <h4>AI 原始返回</h4>
            </div>
            <pre class="llm-trace-raw">${escapeHtml(responseText)}</pre>
          </section>
        </div>
      </article>
    `;
  }

  function renderLlmTraceModal() {
    const payload = state.llmTraceModalPayload;
    if (!payload) {
      elements.llmTraceTitle.textContent = "LLM 调用详情";
      elements.llmTraceCaption.textContent = "这里会显示本轮提交，以及发送给 AI 和 AI 返回的完整原文。";
      elements.llmTraceMode.textContent = "本轮详情";
      elements.llmTraceBody.innerHTML = '<div class="empty-state">完成一次 LLM 问答后，可在这里查看完整详情。</div>';
      return;
    }

    elements.llmTraceTitle.textContent = payload.title;
    elements.llmTraceCaption.textContent = payload.caption;
    elements.llmTraceMode.textContent = payload.modeLabel;
    elements.llmTraceBody.innerHTML = `
      <section class="llm-trace-section">
        <div class="llm-trace-section-head">
          <h3>本轮提交</h3>
          <span class="llm-trace-meta">${escapeHtml(payload.submittedAt ? formatDateTime(payload.submittedAt) : "刚刚提交")}</span>
        </div>
        ${renderLlmTraceSummaryFields(payload.submissionFields)}
      </section>
      <section class="llm-trace-section">
        <div class="llm-trace-section-head">
          <h3>调用信息</h3>
          <span class="status-chip ${statusTone(payload.status)}">${escapeHtml(localizeOperationChainStatus(payload.status))}</span>
        </div>
        ${renderLlmTraceSummaryFields(payload.llmFields)}
      </section>
      <section class="llm-trace-section">
        <div class="llm-trace-section-head">
          <h3>完整请求与回答</h3>
          <span class="llm-trace-meta">${escapeHtml(`共 ${payload.exchanges.length} 轮`)}</span>
        </div>
        <div class="llm-trace-exchanges">
          ${payload.exchanges.length
            ? payload.exchanges.map((exchange) => renderLlmTraceExchange(exchange)).join("")
            : '<div class="empty-state">这次没有记录到可展示的请求或回答原文。</div>'}
        </div>
      </section>
      ${payload.finalAnswerText
        ? `
          <section class="llm-trace-section">
            <div class="llm-trace-section-head">
              <h3>最终回答</h3>
            </div>
            <pre class="llm-trace-raw llm-trace-final-answer">${escapeHtml(payload.finalAnswerText)}</pre>
          </section>
        `
        : ""}
    `;
  }

  function setLlmTraceModalOpen(open) {
    state.llmTraceModalOpen = Boolean(open);
    elements.llmTraceModal.hidden = !state.llmTraceModalOpen;
    elements.llmTraceModal.setAttribute("aria-hidden", state.llmTraceModalOpen ? "false" : "true");
    syncModalOpenState();
  }

  function openLlmTraceModal(payload) {
    state.llmTraceModalPayload = payload;
    renderLlmTraceModal();
    setLlmTraceModalOpen(true);
  }

  function closeLlmTraceModal() {
    setLlmTraceModalOpen(false);
  }

  function buildIdleOperationChain(operationId) {
    const config = getOperationChainConfig(operationId);
    const runtimeContext = buildOperationRuntimeContext();

    if (operationId === "module-ingest") {
      return buildOperationChainSnapshot(operationId, {
        status: "idle",
        requestSummary: compactChainDetails([
          { label: "当前阶段", value: "等待填写内容并开始写入" },
          { label: "记录分组", value: elements.ingestEpisodeId.value.trim() || "系统自动新建" },
          { label: "时间顺序", value: elements.ingestTimestampOrder.value || defaults.ingestTimestampOrder },
        ]),
        runtimeContext,
        steps: [
          createOperationChainStep(config.steps[0], {
            status: "active",
            defaultOpen: true,
            details: compactChainDetails([
              { label: "接口", value: config.apiPath },
              { label: "内容", value: "提交后显示内容摘要" },
              { label: "记录分组", value: elements.ingestEpisodeId.value.trim() || "可选" },
              { label: "时间顺序", value: "大于 0 的整数" },
            ]),
          }),
          createOperationChainStep(config.steps[1], {
            details: compactChainDetails([{ label: "写入结果", value: "提交后显示 object_id 与 version" }]),
          }),
          createOperationChainStep(config.steps[2], {
            details: compactChainDetails([{ label: "分组确认", value: "提交后显示 episode_id 与 timestamp_order" }]),
          }),
          createOperationChainStep(config.steps[3], {
            details: compactChainDetails([{ label: "返回内容", value: "object_id / version / trace_ref" }]),
          }),
        ],
      });
    }

    if (operationId === "module-retrieve") {
      return buildOperationChainSnapshot(operationId, {
        status: "idle",
        requestSummary: compactChainDetails([
          { label: "当前阶段", value: "等待填写问题并开始检索" },
          { label: "记录分组", value: elements.retrieveEpisodeId.value.trim() || "全部分组" },
          { label: "最多显示", value: elements.retrieveMaxCandidates.value || defaults.retrieveMaxCandidates },
        ]),
        runtimeContext,
        steps: [
          createOperationChainStep(config.steps[0], {
            status: "active",
            defaultOpen: true,
            details: compactChainDetails([
              { label: "接口", value: config.apiPath },
              { label: "问题", value: "提交后显示问题摘要" },
              { label: "记录分组", value: elements.retrieveEpisodeId.value.trim() || "可选" },
              { label: "最多显示", value: elements.retrieveMaxCandidates.value || defaults.retrieveMaxCandidates },
            ]),
          }),
          createOperationChainStep(config.steps[1], {
            details: compactChainDetails([{ label: "检索方式", value: "按当前问题执行关键词查找" }]),
          }),
          createOperationChainStep(config.steps[2], {
            details: compactChainDetails([{ label: "返回内容", value: "candidate_count / trace_ref" }]),
          }),
        ],
      });
    }

    if (operationId === "module-access") {
      return buildOperationChainSnapshot(operationId, {
        status: "idle",
        requestSummary: compactChainDetails([
          { label: "当前阶段", value: "等待填写问题并开始回答" },
          { label: "回答方式", value: localizeAccessDepth(elements.accessDepth.value) },
        ]),
        runtimeContext,
        steps: [
          createOperationChainStep(config.steps[0], {
            status: "active",
            defaultOpen: true,
            details: compactChainDetails([
              { label: "接口", value: config.apiPath },
              { label: "问题", value: "提交后显示问题摘要" },
              { label: "回答方式", value: localizeAccessDepth(elements.accessDepth.value) },
              { label: "记录分组", value: "可选" },
              { label: "任务编号", value: "可选" },
            ]),
          }),
          createOperationChainStep(config.steps[1], {
            details: compactChainDetails([{ label: "候选内容", value: "提交后显示本次找到的候选数量" }]),
          }),
          createOperationChainStep(config.steps[2], {
            details: compactChainDetails([{ label: "回答依据", value: "提交后显示本次实际采用的内容数量" }]),
          }),
          createOperationChainStep(config.steps[3], {
            status: runtimeContext.answerMode === "llm" ? "upcoming" : "skipped",
            summary: runtimeContext.answerMode === "llm"
              ? config.steps[3].summary
              : "本次如果直接回答，会走内建路径而不会调用外部 LLM。",
            details: compactChainDetails([
              { label: "当前模式", value: localizeAnswerMode(runtimeContext.answerMode) },
              { label: "当前服务", value: runtimeContext.serviceName },
              { label: "模型", value: runtimeContext.model },
              { label: "问题摘要", value: "提交后显示" },
              { label: "回答方式", value: localizeAccessDepth(elements.accessDepth.value) },
              { label: "采用内容数量", value: "提交后显示" },
              { label: "上下文对象数量", value: "提交后显示" },
            ]),
          }),
          createOperationChainStep(config.steps[4], {
            details: compactChainDetails([{ label: "返回内容", value: "answer / support_ids / trace_ref" }]),
          }),
        ],
      });
    }

    if (operationId === "module-benchmark") {
      return buildOperationChainSnapshot(operationId, {
        status: "idle",
        requestSummary: compactChainDetails([
          { label: "当前阶段", value: "先选数据集和 slice，或直接读取历史报告" },
          { label: "数据集", value: elements.benchmarkDatasetName.value.trim() || "未选择" },
          { label: "slice 路径", value: elements.benchmarkSourcePath.value.trim() || "未选择" },
          { label: "报告 run_id", value: elements.benchmarkRunId.value.trim() || "当前数据集暂无报告" },
        ]),
        runtimeContext,
        steps: [
          createOperationChainStep(config.steps[0], {
            status: "active",
            defaultOpen: true,
            details: compactChainDetails([
              { label: "接口", value: config.apiPath },
              { label: "数据集", value: elements.benchmarkDatasetName.value.trim() || "提交后显示" },
              { label: "raw source", value: elements.benchmarkRawSourcePath.value.trim() || "可先生成 slice" },
              { label: "slice 路径", value: elements.benchmarkSourcePath.value.trim() || "提交后显示" },
              { label: "报告 run_id", value: elements.benchmarkRunId.value.trim() || "默认选最近一次" },
            ]),
          }),
          createOperationChainStep(config.steps[1], {
            details: compactChainDetails([
              { label: "写入阶段", value: "执行后显示 raw record 和 episode 的写入说明" },
            ]),
          }),
          createOperationChainStep(config.steps[2], {
            details: compactChainDetails([
              { label: "维护阶段", value: "执行后显示 summarize / reflect / reorganize / schema promotion" },
            ]),
          }),
          createOperationChainStep(config.steps[3], {
            details: compactChainDetails([
              { label: "阶段指标", value: "执行后显示 ask 质量、命中、复用和污染指标" },
            ]),
          }),
          createOperationChainStep(config.steps[4], {
            details: compactChainDetails([
              { label: "返回内容", value: "run_id / report_path / telemetry_path / store_path" },
            ]),
          }),
        ],
      });
    }

    return buildOperationChainSnapshot(operationId, {
      status: "idle",
      requestSummary: compactChainDetails([
        { label: "当前阶段", value: "等待填写整理请求并提交" },
        { label: "任务类型", value: localizeOfflineJobKind(elements.offlineJobKind.value) },
      ]),
      runtimeContext,
      steps: [
        createOperationChainStep(config.steps[0], {
          status: "active",
          defaultOpen: true,
          details: compactChainDetails([
            { label: "接口", value: config.apiPath },
            { label: "任务类型", value: localizeOfflineJobKind(elements.offlineJobKind.value) },
            { label: "优先级", value: elements.offlinePriority.value || defaults.offlinePriority },
          ]),
        }),
        createOperationChainStep(config.steps[1], {
          details: compactChainDetails([{ label: "任务结果", value: "提交后显示 job_id 与 status" }]),
        }),
        createOperationChainStep(config.steps[2], {
          details: compactChainDetails([{ label: "返回内容", value: "job_id / status" }]),
        }),
      ],
    });
  }

  function buildRunningOperationChain(operationId, request, submittedAt = new Date().toISOString()) {
    const config = getOperationChainConfig(operationId);
    const runtimeContext = buildOperationRuntimeContext();
    if (operationId === "module-ingest") {
      return buildOperationChainSnapshot(operationId, {
        status: "running",
        submittedAt,
        runtimeContext,
        requestSummary: compactChainDetails([
          { label: "内容摘要", value: truncateText(request.content, 56) },
          { label: "记录分组", value: request.episode_id || "系统自动新建" },
          { label: "时间顺序", value: request.timestamp_order },
        ]),
        steps: [
          createOperationChainStep(config.steps[0], {
            status: "active",
            defaultOpen: true,
            details: compactChainDetails([
              { label: "接口", value: config.apiPath },
              { label: "内容摘要", value: truncateText(request.content, 56) },
              { label: "记录分组", value: request.episode_id || "系统自动新建" },
              { label: "时间顺序", value: request.timestamp_order },
            ]),
          }),
          createOperationChainStep(config.steps[1]),
          createOperationChainStep(config.steps[2]),
          createOperationChainStep(config.steps[3]),
        ],
        resultSummary: "系统正在处理这次写入请求。",
      });
    }

    if (operationId === "module-retrieve") {
      return buildOperationChainSnapshot(operationId, {
        status: "running",
        submittedAt,
        runtimeContext,
        requestSummary: compactChainDetails([
          { label: "问题摘要", value: truncateText(request.query, 56) },
          { label: "记录分组", value: request.episode_id || "全部分组" },
          { label: "最多显示", value: request.max_candidates },
        ]),
        steps: [
          createOperationChainStep(config.steps[0], {
            status: "done",
            details: compactChainDetails([
              { label: "接口", value: config.apiPath },
              { label: "问题摘要", value: truncateText(request.query, 56) },
              { label: "记录分组", value: request.episode_id || "全部分组" },
              { label: "最多显示", value: request.max_candidates },
            ]),
          }),
          createOperationChainStep(config.steps[1], {
            status: "active",
            defaultOpen: true,
            details: compactChainDetails([{ label: "当前状态", value: "系统正在检索候选内容" }]),
          }),
          createOperationChainStep(config.steps[2]),
        ],
        resultSummary: "系统正在执行这次检索。",
      });
    }

    if (operationId === "module-access") {
      return buildOperationChainSnapshot(operationId, {
        status: "running",
        submittedAt,
        runtimeContext,
        requestSummary: compactChainDetails([
          { label: "问题摘要", value: truncateText(request.query, 56) },
          { label: "回答方式", value: localizeAccessDepth(request.depth) },
          { label: "记录分组", value: request.episode_id || "全部分组" },
          { label: "任务编号", value: request.task_id || "未关联" },
        ]),
        steps: [
          createOperationChainStep(config.steps[0], {
            status: "done",
            details: compactChainDetails([
              { label: "接口", value: config.apiPath },
              { label: "问题摘要", value: truncateText(request.query, 56) },
              { label: "回答方式", value: localizeAccessDepth(request.depth) },
            ]),
          }),
          createOperationChainStep(config.steps[1], {
            status: "active",
            defaultOpen: true,
            details: compactChainDetails([{ label: "当前状态", value: "系统正在查找候选内容" }]),
          }),
          createOperationChainStep(config.steps[2]),
          createOperationChainStep(config.steps[3], {
            status: runtimeContext.answerMode === "llm" ? "upcoming" : "skipped",
            highlighted: true,
          }),
          createOperationChainStep(config.steps[4]),
        ],
        resultSummary: "系统正在为这次问题整理依据。",
      });
    }

    if (operationId === "module-benchmark") {
      const loadingReport = isBenchmarkReportReload(request);
      const apiPath = loadingReport ? "/v1/frontend/benchmark:report" : config.apiPath;
      return buildOperationChainSnapshot(operationId, {
        status: "running",
        submittedAt,
        runtimeContext,
        requestSummary: compactChainDetails([
          { label: loadingReport ? "读取目标" : "数据集", value: loadingReport ? (request.run_id || "最近一次报告") : request.dataset_name },
          { label: "slice 路径", value: loadingReport ? "本次不重跑 benchmark" : request.source_path },
          { label: "报告 run_id", value: request.run_id || (loadingReport ? "最近一次报告" : "运行后返回") },
        ]),
        steps: [
          createOperationChainStep(config.steps[0], {
            status: "done",
            details: compactChainDetails([
              { label: "接口", value: apiPath },
              { label: loadingReport ? "读取目标" : "数据集", value: loadingReport ? (request.run_id || "最近一次报告") : request.dataset_name },
              { label: "slice 路径", value: loadingReport ? "本次不重跑 benchmark" : request.source_path },
              { label: "报告 run_id", value: request.run_id || (loadingReport ? "最近一次报告" : "运行后返回") },
            ]),
          }),
          createOperationChainStep(config.steps[1], loadingReport
            ? {
                status: "skipped",
                summary: "本次只读取已落盘报告，不会重新写入内容。",
              }
            : {
                status: "active",
                defaultOpen: true,
                details: compactChainDetails([{ label: "当前状态", value: "系统正在写入原始内容并补齐 episode" }]),
              }),
          createOperationChainStep(config.steps[2], {
            status: loadingReport ? "skipped" : "upcoming",
            summary: loadingReport ? "本次只读取已落盘报告，不会重新运行维护阶段。" : config.steps[2].summary,
          }),
          createOperationChainStep(config.steps[3], {
            status: loadingReport ? "skipped" : "upcoming",
            highlighted: true,
            summary: loadingReport ? "本次只读取已落盘报告，不会重新计算阶段 ask 指标。" : config.steps[3].summary,
          }),
          createOperationChainStep(config.steps[4], loadingReport
            ? {
                status: "active",
                defaultOpen: true,
                details: compactChainDetails([{ label: "当前状态", value: "系统正在读取已持久化的 benchmark 报告" }]),
              }
            : {}),
        ],
        resultSummary: loadingReport ? "系统正在读取生命周期基准报告。" : "系统正在执行生命周期基准。",
      });
    }

    return buildOperationChainSnapshot(operationId, {
      status: "running",
      submittedAt,
      runtimeContext,
      requestSummary: compactChainDetails([
        { label: "任务类型", value: localizeOfflineJobKind(request.job_kind) },
        { label: "优先级", value: request.priority },
      ]),
      steps: [
        createOperationChainStep(config.steps[0], {
          status: "done",
          details: compactChainDetails([
            { label: "接口", value: config.apiPath },
            { label: "任务类型", value: localizeOfflineJobKind(request.job_kind) },
            { label: "优先级", value: request.priority },
          ]),
        }),
        createOperationChainStep(config.steps[1], {
          status: "active",
          defaultOpen: true,
          details: compactChainDetails([{ label: "当前状态", value: "系统正在创建后台任务" }]),
        }),
        createOperationChainStep(config.steps[2]),
      ],
      resultSummary: "系统正在提交后台任务。",
    });
  }

  function buildSuccessfulOperationChain(operationId, request, result, submittedAt) {
    const config = getOperationChainConfig(operationId);
    const runtimeContext = buildOperationRuntimeContext();
    if (operationId === "module-ingest") {
      return buildOperationChainSnapshot(operationId, {
        status: "success",
        submittedAt,
        runtimeContext,
        requestSummary: compactChainDetails([
          { label: "内容摘要", value: truncateText(request.content, 56) },
          { label: "记录分组", value: result.episode_id },
          { label: "时间顺序", value: request.timestamp_order },
        ]),
        steps: [
          createOperationChainStep(config.steps[0], {
            status: "done",
            details: compactChainDetails([
              { label: "接口", value: config.apiPath },
              { label: "内容摘要", value: truncateText(request.content, 56) },
            ]),
          }),
          createOperationChainStep(config.steps[1], {
            status: "done",
            details: compactChainDetails([
              { label: "object_id", value: result.object_id },
              { label: "version", value: result.version },
            ]),
          }),
          createOperationChainStep(config.steps[2], {
            status: "done",
            details: compactChainDetails([
              { label: "episode_id", value: result.episode_id },
              { label: "timestamp_order", value: request.timestamp_order },
            ]),
          }),
          createOperationChainStep(config.steps[3], {
            status: "done",
            defaultOpen: true,
            details: compactChainDetails([
              { label: "object_id", value: result.object_id },
              { label: "trace_ref", value: result.trace_ref || "未返回" },
            ]),
          }),
        ],
        resultSummary: "系统已完成写入，并返回记录编号。",
      });
    }

    if (operationId === "module-retrieve") {
      return buildOperationChainSnapshot(operationId, {
        status: "success",
        submittedAt,
        runtimeContext,
        requestSummary: compactChainDetails([
          { label: "问题摘要", value: truncateText(request.query, 56) },
          { label: "记录分组", value: request.episode_id || "全部分组" },
          { label: "最多显示", value: request.max_candidates },
        ]),
        steps: [
          createOperationChainStep(config.steps[0], {
            status: "done",
            details: compactChainDetails([
              { label: "接口", value: config.apiPath },
              { label: "问题摘要", value: truncateText(request.query, 56) },
              { label: "记录分组", value: request.episode_id || "全部分组" },
              { label: "最多显示", value: request.max_candidates },
            ]),
          }),
          createOperationChainStep(config.steps[1], {
            status: "done",
            details: compactChainDetails([
              { label: "候选内容", value: result.candidate_count },
              { label: "查找说明", value: truncateText(result.evidence_summary || "系统已完成检索。", 72) },
            ]),
          }),
          createOperationChainStep(config.steps[2], {
            status: "done",
            defaultOpen: true,
            details: compactChainDetails([
              { label: "candidate_count", value: result.candidate_count },
              { label: "trace_ref", value: result.trace_ref || "未返回" },
            ]),
          }),
        ],
        resultSummary: `系统已返回 ${result.candidate_count} 条候选内容。`,
      });
    }

    if (operationId === "module-access") {
      const answer = result.answer || null;
      const answerTrace = answer?.trace || null;
      const supportIds = answer?.support_ids || [];
      const providerFamily = answerTrace?.provider_family || runtimeContext.providerFamily;
      const endpoint = answerTrace?.endpoint || runtimeContext.endpoint || "未返回";
      const usedLlm = ["openai", "claude", "gemini"].includes(providerFamily) || runtimeContext.answerMode === "llm";
      const fallbackUsed = Boolean(answerTrace?.fallback_used);
      const llmSummary = fallbackUsed
        ? `LLM 调用后触发回退：${answerTrace?.fallback_reason || "已改走确定性路径"}`
        : usedLlm
          ? `已调用 ${runtimeContext.serviceName} 生成回答。`
          : "本次未调用 LLM，走内建路径。";
      return buildOperationChainSnapshot(operationId, {
        status: fallbackUsed ? "fallback" : "success",
        submittedAt,
        runtimeContext,
        requestSummary: compactChainDetails([
          { label: "问题摘要", value: truncateText(request.query, 56) },
          { label: "回答方式", value: localizeAccessDepth(request.depth) },
          { label: "记录分组", value: request.episode_id || "全部分组" },
          { label: "任务编号", value: request.task_id || "未关联" },
        ]),
        steps: [
          createOperationChainStep(config.steps[0], {
            status: "done",
            details: compactChainDetails([
              { label: "接口", value: config.apiPath },
              { label: "问题摘要", value: truncateText(request.query, 56) },
              { label: "回答方式", value: localizeAccessDepth(request.depth) },
              { label: "记录分组", value: request.episode_id || "全部分组" },
              { label: "任务编号", value: request.task_id || "未关联" },
            ]),
          }),
          createOperationChainStep(config.steps[1], {
            status: "done",
            details: compactChainDetails([
              { label: "候选数量", value: result.candidate_count },
              { label: "参考范围", value: result.context_object_count },
            ]),
          }),
          createOperationChainStep(config.steps[2], {
            status: "done",
            details: compactChainDetails([
              { label: "实际采用", value: result.selected_count },
              { label: "support_ids", value: supportIds },
            ]),
          }),
          createOperationChainStep(config.steps[3], {
            status: usedLlm ? (fallbackUsed ? "fallback" : "done") : "skipped",
            highlighted: true,
            defaultOpen: fallbackUsed,
            summary: llmSummary,
            details: [
              ...compactChainDetails([
                { label: "服务名", value: runtimeContext.serviceName },
                { label: "协议", value: localizeProviderFamily(providerFamily) },
                { label: "模型", value: runtimeContext.model },
                { label: "endpoint", value: endpoint },
                { label: "是否回退", value: fallbackUsed ? "是" : "否" },
                { label: "回退原因", value: answerTrace?.fallback_reason || (usedLlm ? "无" : "当前未启用外部 LLM") },
                { label: "问题摘要", value: truncateText(request.query, 48) },
                { label: "回答方式", value: localizeAccessDepth(result.resolved_depth || request.depth) },
                { label: "采用内容数量", value: result.selected_count },
                { label: "上下文对象数量", value: result.context_object_count },
              ]),
              usedLlm || answerTrace?.request_text || answerTrace?.response_text
                ? llmTraceModalDetail("查看本轮提交、发送给 AI 的原文，以及 AI 的原始返回")
                : null,
            ].filter(Boolean),
          }),
          createOperationChainStep(config.steps[4], {
            status: "done",
            defaultOpen: !fallbackUsed,
            details: compactChainDetails([
              { label: "回答摘要", value: truncateText(answer?.text || result.summary, 72) },
              { label: "resolved_depth", value: localizeAccessDepth(result.resolved_depth) },
              { label: "support_ids", value: supportIds },
              { label: "trace_ref", value: result.trace_ref || "未返回" },
            ]),
          }),
        ],
        resultSummary: fallbackUsed
          ? `回答已生成，但外部 LLM 触发回退；本次采用了 ${result.selected_count} 条内容。`
          : `回答已生成，本次采用了 ${result.selected_count} 条内容。`,
        llmTracePayload: buildLlmTraceModalPayload({
          request,
          result,
          runtimeContext,
          submittedAt,
        }),
      });
    }

    if (operationId === "module-benchmark") {
      const loadingReport = isBenchmarkReportReload(request);
      const apiPath = loadingReport ? "/v1/frontend/benchmark:report" : config.apiPath;
      const latestStage = getLatestBenchmarkStage(result);
      return buildOperationChainSnapshot(operationId, {
        status: "success",
        submittedAt,
        runtimeContext,
        requestSummary: compactChainDetails([
          { label: loadingReport ? "读取目标" : "数据集", value: loadingReport ? (request.run_id || "最近一次报告") : result.dataset_name },
          { label: "数据分组数", value: result.bundle_count },
          { label: "问答样例数", value: result.answer_case_count },
          { label: "报告 run_id", value: result.run_id },
        ]),
        steps: [
          createOperationChainStep(config.steps[0], {
            status: "done",
            details: compactChainDetails([
              { label: "接口", value: apiPath },
              { label: loadingReport ? "读取目标" : "数据集", value: loadingReport ? (request.run_id || "最近一次报告") : result.dataset_name },
              { label: "slice 路径", value: loadingReport ? "本次未重跑 benchmark" : result.source_path },
              { label: "报告 run_id", value: result.run_id },
            ]),
          }),
          createOperationChainStep(config.steps[1], loadingReport
            ? {
                status: "skipped",
                summary: "本次只读取已落盘报告，没有重新写入原始内容。",
              }
            : {
                status: "done",
                details: compactChainDetails([
                  { label: "数据分组数", value: result.bundle_count },
                  { label: "阶段说明", value: result.stage_reports?.[0]?.operation_notes || "已完成写入阶段" },
                ]),
              }),
          createOperationChainStep(config.steps[2], {
            status: loadingReport ? "skipped" : "done",
            details: loadingReport
              ? []
              : compactChainDetails([
                  { label: "阶段数", value: result.stage_count },
                  { label: "当前阶段", value: result.latest_stage_name },
                  { label: "阶段说明", value: latestStage?.operation_notes || "已完成维护阶段" },
                ]),
          }),
          createOperationChainStep(config.steps[3], {
            status: loadingReport ? "skipped" : "done",
            highlighted: true,
            details: loadingReport
              ? []
              : compactChainDetails([
                  { label: "回答质量", value: latestStage?.ask?.average_answer_quality },
                  { label: "任务成功率", value: latestStage?.ask?.task_success_rate },
                  { label: "污染率", value: latestStage?.ask?.pollution_rate },
                ]),
          }),
          createOperationChainStep(config.steps[4], {
            status: "done",
            defaultOpen: true,
            details: compactChainDetails([
              { label: "run_id", value: result.run_id },
              { label: "report_path", value: result.report_path },
              { label: "telemetry_path", value: result.telemetry_path || "未落盘" },
              { label: "store_path", value: result.store_path || "未落盘" },
              { label: "debug run_id", value: result.frontend_debug_query?.run_id || result.run_id },
            ]),
          }),
        ],
        resultSummary: loadingReport ? "生命周期基准报告已读取。" : "生命周期基准已执行完成，并返回阶段报告。",
      });
    }

    return buildOperationChainSnapshot(operationId, {
      status: "success",
      submittedAt,
      runtimeContext,
      requestSummary: compactChainDetails([
        { label: "任务类型", value: localizeOfflineJobKind(request.job_kind) },
        { label: "优先级", value: request.priority },
        {
          label: "目标范围",
          value: request.job_kind === "reflect_episode"
            ? (request.payload?.episode_id || "未填写")
            : ((request.payload?.target_refs || []).join(", ") || "未填写"),
        },
      ]),
      steps: [
        createOperationChainStep(config.steps[0], {
          status: "done",
          details: compactChainDetails([
            { label: "接口", value: config.apiPath },
            { label: "任务类型", value: localizeOfflineJobKind(request.job_kind) },
            { label: "优先级", value: request.priority },
          ]),
        }),
        createOperationChainStep(config.steps[1], {
          status: "done",
          details: compactChainDetails([{ label: "创建结果", value: "后台任务已创建" }]),
        }),
        createOperationChainStep(config.steps[2], {
          status: "done",
          defaultOpen: true,
          details: compactChainDetails([
            { label: "job_id", value: result.job_id },
            { label: "status", value: result.status },
          ]),
        }),
      ],
      resultSummary: "后台任务已提交到系统，等待后续处理。",
    });
  }

  function buildErrorOperationChain(operationId, request, error, submittedAt) {
    const config = getOperationChainConfig(operationId);
    const runtimeContext = buildOperationRuntimeContext();
    const message = error instanceof Error ? error.message : "这次操作没有成功完成。";

    if (operationId === "module-ingest") {
      return buildOperationChainSnapshot(operationId, {
        status: "error",
        submittedAt,
        runtimeContext,
        requestSummary: compactChainDetails([
          { label: "内容摘要", value: truncateText(request.content, 56) },
          { label: "记录分组", value: request.episode_id || "系统自动新建" },
          { label: "时间顺序", value: request.timestamp_order },
        ]),
        steps: [
          createOperationChainStep(config.steps[0], { status: "done" }),
          createOperationChainStep(config.steps[1], {
            status: "error",
            defaultOpen: true,
            details: compactChainDetails([
              { label: "接口", value: config.apiPath },
              { label: "错误信息", value: message },
            ]),
          }),
          createOperationChainStep(config.steps[2]),
          createOperationChainStep(config.steps[3]),
        ],
        resultSummary: "系统未能完成本次写入。",
        errorMessage: message,
      });
    }

    if (operationId === "module-retrieve") {
      return buildOperationChainSnapshot(operationId, {
        status: "error",
        submittedAt,
        runtimeContext,
        requestSummary: compactChainDetails([
          { label: "问题摘要", value: truncateText(request.query, 56) },
          { label: "记录分组", value: request.episode_id || "全部分组" },
          { label: "最多显示", value: request.max_candidates },
        ]),
        steps: [
          createOperationChainStep(config.steps[0], { status: "done" }),
          createOperationChainStep(config.steps[1], {
            status: "error",
            defaultOpen: true,
            details: compactChainDetails([
              { label: "接口", value: config.apiPath },
              { label: "错误信息", value: message },
            ]),
          }),
          createOperationChainStep(config.steps[2]),
        ],
        resultSummary: "系统未能完成本次检索。",
        errorMessage: message,
      });
    }

    if (operationId === "module-access") {
      const failingStep = buildOperationRuntimeContext().answerMode === "llm" ? "llm" : "retrieve";
      return buildOperationChainSnapshot(operationId, {
        status: "error",
        submittedAt,
        runtimeContext,
        requestSummary: compactChainDetails([
          { label: "问题摘要", value: truncateText(request.query, 56) },
          { label: "回答方式", value: localizeAccessDepth(request.depth) },
          { label: "记录分组", value: request.episode_id || "全部分组" },
        ]),
        steps: config.steps.map((step, index) => {
          if (step.id === "receive") {
            return createOperationChainStep(step, { status: "done" });
          }
          if (step.id === failingStep) {
            return createOperationChainStep(step, {
              status: "error",
              highlighted: step.id === "llm",
              defaultOpen: true,
              details: compactChainDetails([
                { label: "接口", value: config.apiPath },
                { label: "当前模式", value: localizeAnswerMode(runtimeContext.answerMode) },
                { label: "错误信息", value: message },
              ]),
            });
          }
          return createOperationChainStep(step, {
            status: index < config.steps.findIndex((item) => item.id === failingStep) ? "done" : "upcoming",
          });
        }),
        resultSummary: "系统未能完成本次回答。",
        errorMessage: message,
      });
    }

    if (operationId === "module-benchmark") {
      const loadingReport = isBenchmarkReportReload(request);
      const apiPath = loadingReport ? "/v1/frontend/benchmark:report" : config.apiPath;
      return buildOperationChainSnapshot(operationId, {
        status: "error",
        submittedAt,
        runtimeContext,
        requestSummary: compactChainDetails([
          { label: loadingReport ? "读取目标" : "数据集", value: loadingReport ? (request.run_id || "最近一次报告") : request.dataset_name },
          { label: "slice 路径", value: loadingReport ? "本次不重跑 benchmark" : request.source_path },
          { label: "报告 run_id", value: request.run_id || (loadingReport ? "最近一次报告" : "运行后返回") },
        ]),
        steps: [
          createOperationChainStep(config.steps[0], {
            status: loadingReport ? "error" : "done",
            defaultOpen: loadingReport,
            details: compactChainDetails([
              { label: "接口", value: apiPath },
              { label: "错误信息", value: loadingReport ? message : "请求已发出，执行阶段失败" },
            ]),
          }),
          createOperationChainStep(config.steps[1], loadingReport
            ? {
                status: "skipped",
                summary: "本次只读取已落盘报告，没有重新写入内容。",
              }
            : {
                status: "error",
                defaultOpen: true,
                details: compactChainDetails([
                  { label: "接口", value: apiPath },
                  { label: "错误信息", value: message },
                ]),
              }),
          createOperationChainStep(config.steps[2], {
            status: loadingReport ? "skipped" : "upcoming",
          }),
          createOperationChainStep(config.steps[3], {
            status: loadingReport ? "skipped" : "upcoming",
            highlighted: true,
          }),
          createOperationChainStep(config.steps[4], {
            status: loadingReport ? "upcoming" : "upcoming",
          }),
        ],
        resultSummary: loadingReport ? "系统未能读取这次生命周期基准报告。" : "系统未能完成这次生命周期基准。",
        errorMessage: message,
      });
    }

    return buildOperationChainSnapshot(operationId, {
      status: "error",
      submittedAt,
      runtimeContext,
      requestSummary: compactChainDetails([
        { label: "任务类型", value: localizeOfflineJobKind(request.job_kind) },
        { label: "优先级", value: request.priority },
      ]),
      steps: [
        createOperationChainStep(config.steps[0], { status: "done" }),
        createOperationChainStep(config.steps[1], {
          status: "error",
          defaultOpen: true,
          details: compactChainDetails([
            { label: "接口", value: config.apiPath },
            { label: "错误信息", value: message },
          ]),
        }),
        createOperationChainStep(config.steps[2]),
      ],
      resultSummary: "系统未能创建这次后台任务。",
      errorMessage: message,
    });
  }

  function getOperationChainSnapshot(operationId) {
    return state.operationChainSnapshots[operationId] || buildIdleOperationChain(operationId);
  }

  function statusTone(status) {
    if (status === "success" || status === "done") {
      return "status-ok";
    }
    if (status === "fallback") {
      return "status-warn";
    }
    if (status === "error") {
      return "status-err";
    }
    return "";
  }

  function renderOperationChainFields(items, variant = "detail") {
    const listClass = variant === "compact"
      ? "ops-chain-field-list is-compact"
      : "ops-chain-field-list is-detail";
    const itemClass = variant === "compact"
      ? "ops-chain-field is-compact"
      : "ops-chain-field is-detail";
    return `
      <dl class="${listClass}">
        ${items
          .map((item) => {
            if (item.kind === "expander") {
              return `
                <div class="${itemClass} is-expander">
                  <dt>${escapeHtml(item.label)}</dt>
                  <dd>
                    <details class="ops-chain-detail-expander">
                      <summary>${escapeHtml(item.summary || "查看详情")}</summary>
                      <pre class="ops-chain-raw-text">${escapeHtml(item.value)}</pre>
                    </details>
                  </dd>
                </div>
              `;
            }
            if (item.kind === "trace-modal") {
              return `
                <div class="${itemClass} is-modal-launch">
                  <dt>${escapeHtml(item.label)}</dt>
                  <dd>
                    <button type="button" class="ops-chain-trace-launch" data-open-llm-trace>
                      <span class="ops-chain-trace-launch-copy">
                        <strong>查看详情</strong>
                        <span>${escapeHtml(item.summary || "查看本轮完整请求与回答")}</span>
                      </span>
                      <span class="ops-chain-trace-launch-arrow" aria-hidden="true">↗</span>
                    </button>
                  </dd>
                </div>
              `;
            }
            return `
              <div class="${itemClass}">
                <dt>${escapeHtml(item.label)}</dt>
                <dd>${escapeHtml(item.value)}</dd>
              </div>
            `;
          })
          .join("")}
      </dl>
    `;
  }

  function renderOperationChainStep(step, index) {
    const stepTone = statusTone(step.status);
    const statusClass = stepTone ? ` ${stepTone}` : "";
    const highlightClass = step.highlighted ? " is-highlighted" : "";
    const openByDefault = step.defaultOpen && ["active", "fallback", "error"].includes(step.status);
    const openAttr = openByDefault ? " open" : "";
    return `
      <details class="ops-chain-step${highlightClass}${statusClass}"${openAttr}>
        <summary>
          <span class="ops-chain-step-index">${escapeHtml(index + 1)}</span>
          <span class="ops-chain-step-copy">
            <strong>${escapeHtml(step.label)}</strong>
            <span>${escapeHtml(step.summary)}</span>
          </span>
          <span class="status-chip${statusClass}">${escapeHtml(localizeOperationStepStatus(step.status))}</span>
          <span class="ops-chain-step-caret" aria-hidden="true"></span>
        </summary>
        <div class="ops-chain-step-details">
          ${step.details.length
            ? renderOperationChainFields(step.details, "detail")
            : '<p class="text-muted">执行后会在这里补充技术细节。</p>'}
        </div>
      </details>
    `;
  }

  function renderOperationChain(operationId = state.activeOperation) {
    const snapshot = getOperationChainSnapshot(operationId);
    elements.opsChainTitle.textContent = snapshot.title;
    elements.opsChainMeta.innerHTML = `
      <span class="status-chip ${statusTone(snapshot.status)}">${escapeHtml(localizeOperationChainStatus(snapshot.status))}</span>
      <span class="ops-chain-time">${escapeHtml(snapshot.submittedAt ? `提交于 ${formatDateTime(snapshot.submittedAt)}` : "还没执行")}</span>
    `;

    elements.opsChainBody.innerHTML = `
      <section class="ops-chain-section ops-chain-section-primary">
        <div class="ops-chain-section-head">
          <h3>实现大纲</h3>
          <span class="ops-chain-outline-note">点击步骤查看细节</span>
        </div>
        <p class="ops-chain-caption">${escapeHtml(snapshot.resultSummary)}</p>
        <div class="ops-chain-steps">
          ${snapshot.steps.map((step, index) => renderOperationChainStep(step, index)).join("")}
        </div>
      </section>
      ${snapshot.errorMessage
        ? `<p class="ops-chain-error">${escapeHtml(snapshot.errorMessage)}</p>`
        : ""}
      <details class="ops-chain-meta-panel">
        <summary>本次输入</summary>
        ${renderOperationChainFields(snapshot.requestSummary, "compact")}
      </details>
      <details class="ops-chain-meta-panel">
        <summary>运行上下文</summary>
        ${renderOperationChainFields(buildOperationChainRuntimeFields(snapshot.runtimeContext), "compact")}
      </details>
    `;
  }

  function setOperationChainSnapshot(operationId, snapshot) {
    state.operationChainSnapshots[operationId] = snapshot;
    if (state.activeOperation === operationId) {
      renderOperationChain(operationId);
    }
  }

  function focusOperationChainShell() {
    if (!elements.opsChainShell || elements.opsChainShell.hidden) {
      return;
    }
    elements.opsChainShell.classList.remove("is-targeted");
    window.clearTimeout(operationChainFocusTimer);
    window.requestAnimationFrame(() => {
      elements.opsChainShell.scrollIntoView({ behavior: "smooth", block: "start", inline: "nearest" });
      elements.opsChainShell.classList.add("is-targeted");
      operationChainFocusTimer = window.setTimeout(() => {
        elements.opsChainShell.classList.remove("is-targeted");
      }, 1400);
    });
  }

  function syncOperationChainOpenButtons() {
    const drawerViewport = isOperationDrawerViewport();
    const shouldShow = drawerViewport || state.operationChainHidden;
    elements.opsChainOpenButtons.forEach((button) => {
      button.hidden = !shouldShow;
      const label = drawerViewport ? "查看链路" : "展开链路";
      button.textContent = label;
      button.dataset.defaultLabel = label;
    });
  }

  function syncOperationChainVisibility() {
    const drawerViewport = isOperationDrawerViewport();
    const hidden = !drawerViewport && state.operationChainHidden;
    elements.opsChainShell.hidden = hidden;
    elements.opsChainShell.classList.toggle("is-collapsed", hidden);
    if (elements.opsChainRestore) {
      elements.opsChainRestore.hidden = drawerViewport || !hidden;
    }
    syncOperationChainOpenButtons();
  }

  function setOperationChainDrawerOpen(open) {
    state.operationChainDrawerOpen = open;
    elements.opsChainShell.classList.toggle("is-open", open);
    elements.opsChainBackdrop.hidden = !open;
    elements.opsChainBackdrop.classList.toggle("is-open", open);
  }

  function setOperationChainHidden(hidden) {
    state.operationChainHidden = Boolean(hidden);
    syncOperationChainVisibility();
  }

  function handleOpenButton(operationId, setActiveWorkspace, setActiveOperation) {
    setActiveWorkspace("workspace-operations");
    setActiveOperation(operationId);
    if (isOperationDrawerViewport()) {
      setOperationChainDrawerOpen(true);
      return;
    }
    if (state.operationChainHidden) {
      setOperationChainHidden(false);
    }
    focusOperationChainShell();
  }

  function handleBodyClick(event) {
    const trigger = event.target instanceof Element
      ? event.target.closest("[data-open-llm-trace]")
      : null;
    if (!(trigger instanceof HTMLButtonElement)) {
      return;
    }
    const snapshot = getOperationChainSnapshot(state.activeOperation);
    if (!snapshot.llmTracePayload) {
      return;
    }
    openLlmTraceModal(snapshot.llmTracePayload);
  }

  function handleEscape() {
    if (state.llmTraceModalOpen) {
      closeLlmTraceModal();
      return true;
    }
    if (state.operationChainDrawerOpen) {
      setOperationChainDrawerOpen(false);
      return true;
    }
    return false;
  }

  function reset() {
    state.operationChainSnapshots = {
      "module-ingest": null,
      "module-retrieve": null,
      "module-access": null,
      "module-offline": null,
    };
    state.operationChainHidden = false;
    state.llmTraceModalPayload = null;
    setLlmTraceModalOpen(false);
    setOperationChainDrawerOpen(false);
    syncOperationChainVisibility();
  }

  return {
    buildErrorOperationChain,
    buildRunningOperationChain,
    buildSuccessfulOperationChain,
    closeLlmTraceModal,
    handleBodyClick,
    handleEscape,
    handleOpenButton,
    focusOperationChainShell,
    renderOperationChain,
    reset,
    setOperationChainDrawerOpen,
    setOperationChainHidden,
    setOperationChainSnapshot,
    syncOperationChainVisibility,
  };
}
