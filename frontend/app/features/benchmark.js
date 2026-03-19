const EMPTY_BENCHMARK_RESULT = '<div class="empty-state">还没有生命周期基准结果。</div>';
const DEFAULT_SLICE_STATUS = "生成后会自动加入上方 slice 下拉。";

function parseSelectorValues(rawValue) {
  return rawValue
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parsePositiveIntegerOrNull(rawValue) {
  const value = Number.parseInt(String(rawValue || "").trim(), 10);
  return Number.isInteger(value) && value > 0 ? value : null;
}

function resolvePreferredValue(validValues, candidates) {
  for (const candidate of candidates) {
    if (candidate && validValues.includes(candidate)) {
      return candidate;
    }
  }
  return validValues[0] || "";
}

function renderSelectOptions(select, options, selectedValue, placeholderLabel) {
  const entries = Array.isArray(options) ? options : [];
  const fragment = document.createDocumentFragment();
  if (!entries.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = placeholderLabel;
    fragment.append(option);
    select.replaceChildren(fragment);
    select.value = "";
    return;
  }
  entries.forEach((item) => {
    const value = typeof item === "string" ? item : item.value;
    const label = typeof item === "string" ? item : item.label;
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    option.selected = value === selectedValue;
    fragment.append(option);
  });
  select.replaceChildren(fragment);
}

function ensureSelectOption(select, value, label) {
  if (!value) {
    return;
  }
  const exists = [...select.options].some((option) => option.value === value);
  if (exists) {
    return;
  }
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  select.append(option);
}

function formatSliceLabel(option) {
  const bundleCount = Number.isFinite(option.bundle_count) ? ` / ${option.bundle_count} 组` : "";
  return `${option.label}${bundleCount}`;
}

function formatReportLabel(option) {
  return option.is_latest ? `${option.label} / 最近一次` : option.label;
}

export function createBenchmarkFeature({
  state,
  elements,
  navigate,
  bindClickAction,
  bindFormAction,
  busyTimes,
  setOperationChainSnapshot,
  buildRunningOperationChain,
  buildSuccessfulOperationChain,
  buildErrorOperationChain,
  loadMemoryLifecycleBenchmarkWorkspace,
  generateMemoryLifecycleBenchmarkSlice,
  runMemoryLifecycleBenchmark,
  loadMemoryLifecycleBenchmarkReport,
  syncActionAvailability,
  renderMetricList,
  escapeHtml,
  formatValue,
}) {
  let workspace = null;

  function getDatasetOptions() {
    return workspace?.datasets || [];
  }

  function getDatasetMeta(datasetName) {
    return getDatasetOptions().find((item) => item.dataset_name === datasetName) || null;
  }

  function getRawSourceOptions(datasetName) {
    return (workspace?.raw_sources || []).filter((item) => item.dataset_name === datasetName);
  }

  function getSliceOptions(datasetName) {
    return (workspace?.slice_options || []).filter((item) => item.dataset_name === datasetName);
  }

  function getReportOptions(datasetName) {
    return (workspace?.report_options || []).filter((item) => item.dataset_name === datasetName);
  }

  function renderSliceStatus(message, kind = "note") {
    if (!elements.benchmarkSliceStatus) {
      return;
    }
    if (kind === "ok") {
      elements.benchmarkSliceStatus.innerHTML = `<span class="status status-ok">${escapeHtml(message)}</span>`;
      return;
    }
    if (kind === "warn") {
      elements.benchmarkSliceStatus.innerHTML = `<span class="status status-warn">${escapeHtml(message)}</span>`;
      return;
    }
    elements.benchmarkSliceStatus.textContent = message;
  }

  function syncDatasetDetails(datasetMeta, reportOptions) {
    elements.benchmarkDatasetHelp.textContent = datasetMeta
      ? datasetMeta.summary
      : "连接后会自动列出可运行的数据集。";
    elements.benchmarkSliceHelp.textContent = datasetMeta?.default_slice_path
      ? `当前数据集默认 sample slice：${datasetMeta.default_slice_path}`
      : "运行 benchmark 时会读取这里选中的 local slice。";
    elements.benchmarkReportHelp.textContent = reportOptions.length
      ? "默认已选中当前数据集最近一次生命周期报告。"
      : "当前数据集还没有历史报告，先运行一次基准即可生成。";
    elements.benchmarkRawSourceHelp.textContent = datasetMeta
      ? (
        datasetMeta.raw_source_kind === "directory"
          ? "当前数据集使用目录型 raw source；生成时会读取目录下的原始文件。"
          : "当前数据集使用 JSON 文件型 raw source；生成时会读取选中的原始样例。"
      )
      : "系统会根据当前数据集切换样例目录或 JSON 文件。";
    elements.benchmarkSliceSelectorLabel.textContent = datasetMeta?.selector_label || "筛选编号";
    elements.benchmarkSliceSelectorValues.placeholder = (
      datasetMeta?.selector_placeholder || "可选，多个编号用逗号分隔"
    );
    elements.benchmarkSliceSelectorHelp.textContent = datasetMeta?.selector_kind
      ? `当前数据集支持通过 ${datasetMeta.selector_label} 精确生成 slice；不填时会按最大条目截取。`
      : "当前数据集不需要额外筛选编号。";
    elements.benchmarkSliceSelectorValues.disabled = !state.apiKey || !datasetMeta?.selector_kind;
  }

  function syncDatasetSelection(preferences = {}) {
    const datasets = getDatasetOptions();
    const datasetName = resolvePreferredValue(
      datasets.map((item) => item.dataset_name),
      [
        preferences.datasetName,
        elements.benchmarkDatasetName.value,
        workspace?.default_dataset_name,
      ],
    );
    renderSelectOptions(
      elements.benchmarkDatasetName,
      datasets.map((item) => ({ value: item.dataset_name, label: item.label })),
      datasetName,
      "暂无可选数据集",
    );

    const datasetMeta = getDatasetMeta(datasetName);
    const rawSourceOptions = getRawSourceOptions(datasetName);
    const sliceOptions = getSliceOptions(datasetName);
    const reportOptions = getReportOptions(datasetName);
    const rawSourcePath = resolvePreferredValue(
      rawSourceOptions.map((item) => item.source_path),
      [
        preferences.rawSourcePath,
        elements.benchmarkRawSourcePath.value,
        datasetMeta?.default_raw_source_path,
        workspace?.default_raw_source_path,
      ],
    );
    const slicePath = resolvePreferredValue(
      sliceOptions.map((item) => item.source_path),
      [
        preferences.slicePath,
        elements.benchmarkSourcePath.value,
        datasetMeta?.default_slice_path,
        workspace?.default_slice_path,
      ],
    );
    const reportRunId = resolvePreferredValue(
      reportOptions.map((item) => item.run_id),
      [
        preferences.reportRunId,
        elements.benchmarkRunId.value,
        workspace?.default_report_run_id,
      ],
    );

    renderSelectOptions(
      elements.benchmarkRawSourcePath,
      rawSourceOptions.map((item) => ({ value: item.source_path, label: item.label })),
      rawSourcePath,
      "当前数据集暂无 raw source",
    );
    renderSelectOptions(
      elements.benchmarkSourcePath,
      sliceOptions.map((item) => ({ value: item.source_path, label: formatSliceLabel(item) })),
      slicePath,
      "当前数据集暂无可选 slice",
    );
    renderSelectOptions(
      elements.benchmarkRunId,
      reportOptions.map((item) => ({ value: item.run_id, label: formatReportLabel(item) })),
      reportRunId,
      "当前数据集暂无历史报告",
    );

    if (preferences.forceOutputPath || !elements.benchmarkSliceOutputPath.value.trim()) {
      elements.benchmarkSliceOutputPath.value = preferences.outputPath
        || datasetMeta?.default_output_path
        || workspace?.default_output_path
        || "";
    }
    if (preferences.clearSelectorValues) {
      elements.benchmarkSliceSelectorValues.value = "";
    }
    if (preferences.clearMaxItems) {
      elements.benchmarkSliceMaxItems.value = "";
    }
    syncDatasetDetails(datasetMeta, reportOptions);
    if (preferences.clearSliceStatus) {
      renderSliceStatus(DEFAULT_SLICE_STATUS);
    }
    syncActionAvailability();
  }

  function renderWorkspace(nextWorkspace, preferences = {}) {
    workspace = nextWorkspace;
    syncDatasetSelection(preferences);
  }

  function clearWorkspace() {
    workspace = null;
    elements.benchmarkResult.innerHTML = EMPTY_BENCHMARK_RESULT;
    elements.debugRunId.value = "";
    renderSelectOptions(elements.benchmarkDatasetName, [], "", "连接后加载");
    renderSelectOptions(elements.benchmarkRawSourcePath, [], "", "先选择数据集");
    renderSelectOptions(elements.benchmarkSourcePath, [], "", "先选择数据集");
    renderSelectOptions(elements.benchmarkRunId, [], "", "暂无历史报告");
    elements.benchmarkSliceOutputPath.value = "";
    elements.benchmarkSliceSelectorValues.value = "";
    elements.benchmarkSliceMaxItems.value = "";
    syncDatasetDetails(null, []);
    renderSliceStatus(DEFAULT_SLICE_STATUS);
    syncActionAvailability();
  }

  async function refreshWorkspace(preferences = {}) {
    if (!state.apiKey) {
      clearWorkspace();
      return null;
    }
    const result = await loadMemoryLifecycleBenchmarkWorkspace(state.apiKey);
    renderWorkspace(result, preferences);
    return result;
  }

  function collectLaunchRequest() {
    const datasetName = elements.benchmarkDatasetName.value.trim();
    const sourcePath = elements.benchmarkSourcePath.value.trim();
    if (!datasetName) {
      throw new Error("请先选择数据集。");
    }
    if (!sourcePath) {
      throw new Error("请先选择本地 slice。");
    }
    return {
      dataset_name: datasetName,
      source_path: sourcePath,
    };
  }

  function collectReportRequest() {
    const runId = elements.benchmarkRunId.value.trim();
    if (!runId) {
      throw new Error("当前数据集还没有可读取的生命周期报告。");
    }
    return { run_id: runId };
  }

  function collectSliceGenerationRequest() {
    const datasetName = elements.benchmarkDatasetName.value.trim();
    const rawSourcePath = elements.benchmarkRawSourcePath.value.trim();
    const outputPath = elements.benchmarkSliceOutputPath.value.trim();
    if (!datasetName) {
      throw new Error("请先选择数据集，再生成 slice。");
    }
    if (!rawSourcePath) {
      throw new Error("请先选择原始数据源。");
    }
    if (!outputPath) {
      throw new Error("请先填写输出 slice 路径。");
    }
    const maxItems = parsePositiveIntegerOrNull(elements.benchmarkSliceMaxItems.value);
    return {
      dataset_name: datasetName,
      raw_source_path: rawSourcePath,
      output_path: outputPath,
      selector_values: parseSelectorValues(elements.benchmarkSliceSelectorValues.value),
      ...(maxItems ? { max_items: maxItems } : {}),
    };
  }

  function renderBenchmarkResult(result) {
    const stages = result.stage_reports || [];
    const latestStage = stages[stages.length - 1] || null;
    elements.benchmarkResult.innerHTML = `
      <div class="status status-ok">生命周期基准已完成，可继续按报告下拉重新加载。</div>
      ${renderMetricList([
        { label: "运行编号", value: result.run_id },
        { label: "数据集", value: result.dataset_name },
        { label: "本地 slice", value: result.source_path },
        { label: "数据分组数", value: result.bundle_count },
        { label: "问答样例数", value: result.answer_case_count },
        { label: "阶段数", value: result.stage_count },
        { label: "当前阶段", value: result.latest_stage_name },
        { label: "报告路径", value: result.report_path },
        { label: "调试 run_id", value: result.frontend_debug_query?.run_id || result.run_id },
      ])}
      <div class="result-grid">
        ${stages.map((stage) => `
          <div class="result-block">
            <h3>${escapeHtml(stage.stage_name)}</h3>
            ${renderMetricList([
              { label: "回答质量", value: stage.ask.average_answer_quality },
              { label: "任务成功率", value: stage.ask.task_success_rate },
              { label: "候选命中率", value: stage.ask.candidate_hit_rate },
              { label: "采用命中率", value: stage.ask.selected_hit_rate },
              { label: "复用率", value: stage.ask.reuse_rate },
              { label: "污染率", value: stage.ask.pollution_rate },
              { label: "活跃对象数", value: stage.memory.active_object_count },
              { label: "版本总数", value: stage.memory.total_object_versions },
              { label: "累计成本", value: stage.cost.total_cost },
              { label: "离线任务数", value: stage.cost.offline_job_count },
            ])}
            <p class="meta">对象构成：${escapeHtml(formatValue(stage.memory.active_object_counts))}</p>
            <p class="meta">阶段说明：${escapeHtml((stage.operation_notes || []).join(" / ") || "无")}</p>
          </div>
        `).join("")}
      </div>
      ${latestStage?.cost
        ? `<p class="meta">telemetry：${escapeHtml(result.telemetry_path || "未落盘")} / store：${escapeHtml(result.store_path || "未落盘")}</p>`
        : ""
      }
      ${result.notes?.length
        ? `<div class="result-panel"><h3>补充说明</h3><ul class="notes-list">${result.notes.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>`
        : ""
      }
    `;
  }

  function resetForm() {
    elements.benchmarkResult.innerHTML = EMPTY_BENCHMARK_RESULT;
    elements.debugRunId.value = "";
    if (!workspace) {
      clearWorkspace();
      return;
    }
    syncDatasetSelection({
      datasetName: workspace.default_dataset_name,
      slicePath: workspace.default_slice_path,
      rawSourcePath: workspace.default_raw_source_path,
      reportRunId: workspace.default_report_run_id,
      outputPath: workspace.default_output_path,
      forceOutputPath: true,
      clearSelectorValues: true,
      clearMaxItems: true,
      clearSliceStatus: true,
    });
  }

  async function handleSliceGeneration() {
    const request = collectSliceGenerationRequest();
    const result = await generateMemoryLifecycleBenchmarkSlice(state.apiKey, request);
    renderSliceStatus(
      `slice 已生成：${result.source_path}（${result.bundle_count} 组数据）`,
      "ok",
    );
    await refreshWorkspace({
      datasetName: result.dataset_name,
      slicePath: result.source_path,
      rawSourcePath: result.raw_source_path,
      outputPath: request.output_path,
    });
    ensureSelectOption(
      elements.benchmarkSourcePath,
      result.source_path,
      `刚生成的 slice · ${result.source_path.split("/").pop()}`,
    );
    elements.benchmarkSourcePath.value = result.source_path;
    syncActionAvailability();
    return result;
  }

  elements.benchmarkDatasetName.addEventListener("change", () => {
    syncDatasetSelection({
      datasetName: elements.benchmarkDatasetName.value,
      forceOutputPath: true,
      clearSelectorValues: true,
      clearSliceStatus: true,
    });
  });

  bindClickAction(elements.benchmarkGenerateSlice, "benchmark-generate-slice", {
    before: () => {
      navigate({
        activeWorkspace: "workspace-operations",
        activeOperation: "module-benchmark",
      });
    },
    busyLabel: "生成中",
    minBusyMs: busyTimes.submit,
    readyMessage: "slice 已生成，可直接运行生命周期基准。",
    work: handleSliceGeneration,
  });

  bindFormAction(elements.benchmarkForm, "benchmark-submit", {
    button: elements.benchmarkSubmit,
    before: () => {
      navigate({
        activeWorkspace: "workspace-operations",
        activeOperation: "module-benchmark",
      });
    },
    busyLabel: "运行中",
    minBusyMs: busyTimes.submit,
    work: async () => {
      const request = collectLaunchRequest();
      const submittedAt = new Date().toISOString();
      setOperationChainSnapshot("module-benchmark", buildRunningOperationChain("module-benchmark", request, submittedAt));
      try {
        const result = await runMemoryLifecycleBenchmark(state.apiKey, request);
        elements.benchmarkRunId.value = result.run_id || "";
        elements.debugRunId.value = result.frontend_debug_query?.run_id || result.run_id || "";
        renderBenchmarkResult(result);
        await refreshWorkspace({
          datasetName: result.dataset_name,
          slicePath: result.source_path,
          reportRunId: result.run_id,
          outputPath: elements.benchmarkSliceOutputPath.value.trim(),
        });
        setOperationChainSnapshot("module-benchmark", buildSuccessfulOperationChain("module-benchmark", request, result, submittedAt));
      } catch (error) {
        setOperationChainSnapshot("module-benchmark", buildErrorOperationChain("module-benchmark", request, error, submittedAt));
        throw error;
      }
    },
  });

  bindClickAction(elements.benchmarkRefresh, "benchmark-refresh", {
    before: () => {
      navigate({
        activeWorkspace: "workspace-operations",
        activeOperation: "module-benchmark",
      });
    },
    busyLabel: "读取中",
    minBusyMs: busyTimes.refresh,
    work: async () => {
      const request = collectReportRequest();
      const submittedAt = new Date().toISOString();
      setOperationChainSnapshot("module-benchmark", buildRunningOperationChain("module-benchmark", request, submittedAt));
      try {
        const result = await loadMemoryLifecycleBenchmarkReport(state.apiKey, request);
        elements.benchmarkRunId.value = result.run_id || elements.benchmarkRunId.value;
        elements.debugRunId.value = result.frontend_debug_query?.run_id || result.run_id || "";
        renderBenchmarkResult(result);
        await refreshWorkspace({
          datasetName: result.dataset_name,
          slicePath: result.source_path,
          reportRunId: result.run_id,
          outputPath: elements.benchmarkSliceOutputPath.value.trim(),
        });
        setOperationChainSnapshot("module-benchmark", buildSuccessfulOperationChain("module-benchmark", request, result, submittedAt));
      } catch (error) {
        setOperationChainSnapshot("module-benchmark", buildErrorOperationChain("module-benchmark", request, error, submittedAt));
        throw error;
      }
    },
  });

  bindClickAction(elements.benchmarkReset, "benchmark-reset", {
    busyLabel: "重置中",
    minBusyMs: busyTimes.reset,
    work: async () => {
      resetForm();
    },
  });

  return {
    clearWorkspace,
    collectLaunchRequest,
    collectReportRequest,
    collectSliceGenerationRequest,
    refreshWorkspace,
    renderBenchmarkResult,
    resetForm,
  };
}
