export function createSettingsLlmFeature({
  windowRef,
  state,
  elements,
  llmProtocolLibrary,
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
  renderSettingsOptions,
  renderSettingsPage,
  renderOverview,
  updateShellSignals,
  syncPanelGuards,
  renderOperationChain,
}) {
  function getLlmProtocolCatalog(settings = state.settingsPage) {
    const protocolViews = Array.isArray(settings?.llm?.protocols) ? settings.llm.protocols : [];
    const protocolOrder = protocolViews.length
      ? protocolViews.map((view) => String(view.protocol))
      : Object.keys(llmProtocolLibrary);

    return Object.fromEntries(
      protocolOrder.map((protocol) => {
        const fallback = llmProtocolLibrary[protocol] || llmProtocolLibrary.openai;
        const view = protocolViews.find((item) => item.protocol === protocol);
        return [
          protocol,
          {
            protocol,
            name: fallback.name,
            mark: fallback.mark,
            accent: fallback.accent,
            summary: fallback.summary,
            label: view?.label || `${fallback.name} 协议`,
            defaultName: view?.default_name || fallback.defaultName,
            defaultIcon: view?.default_icon || fallback.mark,
            defaultEndpoint: view?.default_endpoint || fallback.defaultEndpoint,
            authMode: view?.auth_mode || "api_key",
          },
        ];
      }),
    );
  }

  function getLlmProtocolMeta(protocol, settings = state.settingsPage) {
    const catalog = getLlmProtocolCatalog(settings);
    return catalog[protocol] || catalog.openai || Object.values(catalog)[0];
  }

  function getLlmServices(settings = state.settingsPage) {
    return Array.isArray(settings?.llm?.services) ? settings.llm.services : [];
  }

  function getLlmServiceById(serviceId, settings = state.settingsPage) {
    return getLlmServices(settings).find((service) => service.service_id === serviceId) || null;
  }

  function getLlmActiveService(settings = state.settingsPage) {
    const activeServiceId = settings?.llm?.active_service_id;
    return activeServiceId ? getLlmServiceById(activeServiceId, settings) : null;
  }

  function getLlmSelectedService(settings = state.settingsPage) {
    const selectedServiceId = settings?.llm?.selected_service_id;
    return selectedServiceId ? getLlmServiceById(selectedServiceId, settings) : null;
  }

  function getLiveLlmSelection(settings = state.settingsPage) {
    const activeService = getLlmActiveService(settings);
    if (!activeService) {
      return null;
    }
    return {
      serviceId: activeService.service_id,
      protocol: activeService.protocol,
      name: activeService.name,
      model: activeService.active_model || "",
    };
  }

  function buildLlmDraftForProtocol(protocol, settings = state.settingsPage) {
    const meta = getLlmProtocolMeta(protocol, settings);
    return {
      serviceId: "",
      protocol: meta.protocol,
      name: meta.defaultName,
      icon: "",
      endpoint: meta.defaultEndpoint,
      apiKey: "",
      model: "",
      modelOptions: [],
      apiKeySaved: false,
      apiKeyMasked: "",
      usesOfficialEndpoint: true,
      modelsSynced: false,
    };
  }

  function buildLlmDraftFromService(service, settings = state.settingsPage) {
    const meta = getLlmProtocolMeta(service.protocol, settings);
    return {
      serviceId: service.service_id,
      protocol: service.protocol,
      name: service.name,
      icon: normalizeLlmIconValue(service.icon),
      endpoint: service.endpoint,
      apiKey: "",
      model: service.active_model || service.model_options[0] || "",
      modelOptions: Array.isArray(service.model_options) ? [...service.model_options] : [],
      apiKeySaved: Boolean(service.api_key_saved),
      apiKeyMasked: service.api_key_masked || "",
      usesOfficialEndpoint: Boolean(service.uses_official_endpoint),
      modelsSynced: Boolean(service.models_synced),
      defaultEndpoint: meta.defaultEndpoint,
    };
  }

  function cloneLlmDraft(draft) {
    return {
      ...draft,
      modelOptions: Array.isArray(draft?.modelOptions) ? [...draft.modelOptions] : [],
    };
  }

  function syncLlmServiceSelections(settings = state.settingsPage) {
    const nextSelections = {};
    getLlmServices(settings).forEach((service) => {
      const current = state.llmServiceModelSelections[service.service_id];
      const options = Array.isArray(service.model_options) ? service.model_options : [];
      if (options.length) {
        nextSelections[service.service_id] = options.includes(current)
          ? current
          : (service.active_model || options[0]);
      } else {
        nextSelections[service.service_id] = service.active_model || "";
      }
    });
    state.llmServiceModelSelections = nextSelections;
  }

  function setLlmEditorDraft(draft) {
    state.llmEditorDraft = cloneLlmDraft(draft);
    return state.llmEditorDraft;
  }

  function buildLlmDraftWithSavedState(savedDraft, draft) {
    return {
      ...savedDraft,
      ...draft,
      defaultEndpoint: savedDraft.defaultEndpoint,
      modelOptions: Array.isArray(draft?.modelOptions) && draft.modelOptions.length
        ? [...draft.modelOptions]
        : [...savedDraft.modelOptions],
      apiKeySaved: savedDraft.apiKeySaved,
      apiKeyMasked: savedDraft.apiKeyMasked,
      usesOfficialEndpoint: savedDraft.usesOfficialEndpoint,
      modelsSynced: savedDraft.modelsSynced,
    };
  }

  function computeLlmEditorDraftDirty(draft, settings = state.settingsPage) {
    if (!draft) {
      return false;
    }
    if (!draft.serviceId) {
      const baseline = buildLlmDraftForProtocol(draft.protocol, settings);
      return Boolean(
        draft.name.trim()
        || draft.icon.trim()
        || draft.endpoint.trim()
        || draft.apiKey.trim()
        || draft.model
      ) && (
        draft.name.trim() !== baseline.name
        || draft.icon.trim() !== baseline.icon
        || draft.endpoint.trim() !== baseline.endpoint
        || Boolean(draft.apiKey.trim())
        || Boolean(draft.model)
      );
    }
    const saved = getLlmServiceById(draft.serviceId, settings);
    if (!saved) {
      return false;
    }
    return (
      draft.name.trim() !== saved.name
      || normalizeLlmIconValue(draft.icon) !== normalizeLlmIconValue(saved.icon)
      || draft.endpoint.trim() !== saved.endpoint
      || Boolean(draft.apiKey.trim())
      || (draft.model || "") !== (saved.active_model || saved.model_options[0] || "")
    );
  }

  function ensureLlmEditorDraft(settings = state.settingsPage) {
    const catalog = getLlmProtocolCatalog(settings);
    const firstProtocol = Object.keys(catalog)[0] || "openai";

    if (state.llmEditorDraft?.serviceId) {
      const currentService = getLlmServiceById(state.llmEditorDraft.serviceId, settings);
      if (currentService) {
        const savedDraft = buildLlmDraftFromService(currentService, settings);
        if (computeLlmEditorDraftDirty(state.llmEditorDraft, settings)) {
          return setLlmEditorDraft(buildLlmDraftWithSavedState(savedDraft, state.llmEditorDraft));
        }
        return setLlmEditorDraft(savedDraft);
      }
    }

    if (state.llmEditorDraft?.protocol && catalog[state.llmEditorDraft.protocol]) {
      const fallback = buildLlmDraftForProtocol(state.llmEditorDraft.protocol, settings);
      return setLlmEditorDraft(buildLlmDraftWithSavedState(fallback, state.llmEditorDraft));
    }

    const preferredService = getLlmSelectedService(settings) || getLlmActiveService(settings);
    if (preferredService) {
      return setLlmEditorDraft(buildLlmDraftFromService(preferredService, settings));
    }
    return setLlmEditorDraft(buildLlmDraftForProtocol(firstProtocol, settings));
  }

  function primeLlmEditorFromSettings(settings = state.settingsPage, options = {}) {
    syncLlmServiceSelections(settings);
    if (options.serviceId) {
      const service = getLlmServiceById(options.serviceId, settings);
      if (service) {
        return setLlmEditorDraft(buildLlmDraftFromService(service, settings));
      }
    }
    if (options.protocol) {
      return setLlmEditorDraft(buildLlmDraftForProtocol(options.protocol, settings));
    }
    return ensureLlmEditorDraft(settings);
  }

  function setLlmModalOpen(open) {
    state.llmModalOpen = Boolean(open);
    elements.llmServiceModal.hidden = !state.llmModalOpen;
    elements.llmServiceModal.setAttribute("aria-hidden", state.llmModalOpen ? "false" : "true");
    syncModalOpenState();
  }

  function openLlmEditor(options = {}, message = null, messageKind = "status-ok") {
    primeLlmEditorFromSettings(state.settingsPage, options);
    setLlmModalOpen(true);
    renderLlmPage(message, messageKind);
    windowRef.requestAnimationFrame(() => {
      elements.llmServiceName.focus();
      elements.llmServiceName.select();
    });
  }

  function closeLlmEditor() {
    setLlmModalOpen(false);
    renderLlmPage();
  }

  function updateLlmEditorDraft(updates = {}) {
    const draft = ensureLlmEditorDraft();
    const nextModelOptions = Object.prototype.hasOwnProperty.call(updates, "modelOptions")
      ? updates.modelOptions
      : draft.modelOptions;
    return setLlmEditorDraft({
      ...draft,
      ...updates,
      modelOptions: Array.isArray(nextModelOptions) ? [...nextModelOptions] : [],
    });
  }

  function getSelectedLlmDraft() {
    return ensureLlmEditorDraft();
  }

  function isLlmEditorDraftDirty(settings = state.settingsPage) {
    return computeLlmEditorDraftDirty(getSelectedLlmDraft(), settings);
  }

  function syncLlmEditorDraftUi(settings = state.settingsPage) {
    const draft = getSelectedLlmDraft();
    const protocolMeta = getLlmProtocolMeta(draft.protocol, settings);
    const draftDirty = isLlmEditorDraftDirty(settings);
    elements.llmEditorTitle.textContent = draft.serviceId
      ? `编辑 ${draft.name || "服务"}`
      : `新建 ${protocolMeta.name} 服务`;
    elements.llmEditorMode.textContent = draft.serviceId
      ? (draftDirty ? "未保存更改" : "已保存服务")
      : (draftDirty ? "新建草稿" : "官方模板");
  }

  function renderLlmIconPreview(draft = getSelectedLlmDraft()) {
    const iconValue = normalizeLlmIconValue(draft.icon);
    elements.llmIconPreview.classList.toggle("has-image", Boolean(iconValue));
    elements.llmIconPreview.innerHTML = iconValue
      ? `<img src="${escapeHtml(iconValue)}" alt="${escapeHtml(`${draft.name || "服务"} 图标预览`)}">`
      : `<span>${escapeHtml(buildLlmAvatar(draft.name || "服务", "L"))}</span>`;
    elements.llmIconHelp.textContent = iconValue
      ? "已上传图片。保存后会持久化到当前服务；未上传时会回退为服务名称首字母。"
      : "未上传图片时，会使用服务名称首字母。大图片会在浏览器里自动压缩。";
    elements.llmIconRemove.disabled = !iconValue;
  }

  function buildSelectedLlmApplyRequest({ includeDevMode = false } = {}) {
    const selectedService = getLlmActiveService(state.settingsPage) || getLlmSelectedService(state.settingsPage);
    if (!selectedService) {
      return null;
    }
    const selectedModel = state.llmServiceModelSelections[selectedService.service_id]
      || selectedService.active_model
      || selectedService.model_options[0]
      || "";
    if (!selectedModel) {
      return null;
    }
    const body = {
      service_id: selectedService.service_id,
      provider: selectedService.protocol,
      model: selectedModel,
    };
    if (includeDevMode) {
      body.dev_mode = Boolean(elements.settingsDevMode.checked);
    }
    return body;
  }

  function getLlmEditorCaption(draft, protocolMeta) {
    return draft.serviceId
      ? "修改名称、图标、地址、密钥或模型后，只会更新这项服务，不会自动切换当前激活项。"
      : `${protocolMeta.label} 会先带入官方默认地址和名称；图标可上传图片，不上传时会使用服务名称首字母。`;
  }

  function confirmDeleteLlmService(service) {
    if (!service) {
      return false;
    }
    const prompt = service.is_active
      ? `确认删除「${service.name}」吗？删除后当前工作台会立即切回内建模式。`
      : `确认删除「${service.name}」吗？删除后这项服务会从当前列表移除。`;
    return windowRef.confirm(prompt);
  }

  function renderLlmStatus(message = null, messageKind = "status-ok") {
    const draft = ensureLlmEditorDraft();
    const protocolMeta = getLlmProtocolMeta(draft.protocol);
    const activeService = getLlmActiveService(state.settingsPage);
    state.llmNotice = message ? { message, kind: messageKind } : null;
    elements.llmEditorCaption.textContent = message || getLlmEditorCaption(draft, protocolMeta);
    elements.llmEditorCaption.className = `llm-editor-caption text-muted${message ? ` ${messageKind}` : ""}`;
    const inlineMessage = message
      || (
        activeService
          ? `当前激活：${activeService.name} / ${activeService.active_model || "未选模型"}`
          : "还没有激活的 LLM 服务。先保存服务并获取模型，再决定当前工作台使用哪一项。"
      );
    const inlineKind = message ? messageKind : (activeService ? "status-ok" : "status-warn");
    elements.llmInlineStatus.innerHTML = `<div class="status ${escapeHtml(inlineKind)}">${escapeHtml(inlineMessage)}</div>`;
  }

  function renderLlmPage(message = state.llmNotice?.message || null, messageKind = state.llmNotice?.kind || "status-ok") {
    const settings = state.settingsPage;
    const answerMode = getAnswerModeFromSettings(settings);
    const catalog = getLlmProtocolCatalog(settings);
    const protocols = Object.values(catalog);
    const services = getLlmServices(settings);
    const activeService = getLlmActiveService(settings);
    const draft = ensureLlmEditorDraft(settings);
    const protocolMeta = getLlmProtocolMeta(draft.protocol, settings);
    const activeProtocol = activeService ? getLlmProtocolMeta(activeService.protocol, settings) : null;

    elements.llmModeBadge.textContent = !state.apiKey
      ? "需要访问口令"
      : answerMode === "llm"
        ? "LLM 已启用"
        : "当前仍在使用内建模式";

    elements.llmSummaryGrid.innerHTML = `
      <article class="llm-summary-card">
        <div class="llm-summary-kicker">当前激活服务</div>
        <strong>${escapeHtml(
          answerMode === "llm" && activeService
            ? activeService.name
            : localizeAnswerMode(answerMode),
        )}</strong>
        <p>${escapeHtml(
          answerMode === "llm" && activeService
            ? `${activeProtocol?.label || localizeProviderFamily(settings.provider.provider_family)} / ${activeService.active_model || "未选模型"} / ${activeService.endpoint}`
            : "当前仍使用内建模式",
        )}</p>
      </article>
      <article class="llm-summary-card llm-summary-card-accent">
        <div class="llm-summary-kicker">当前模板</div>
        <strong>${escapeHtml(protocolMeta.label)}</strong>
        <p>${escapeHtml(
          `新建服务时会先带入 ${protocolMeta.defaultName} 和默认地址 ${protocolMeta.defaultEndpoint}。`,
        )}</p>
      </article>
    `;

    elements.llmProtocolGrid.innerHTML = protocols
      .map((protocol) => {
        const protocolServices = services.filter((service) => service.protocol === protocol.protocol);
        const isSelected = draft.protocol === protocol.protocol;
        const isActive = activeService?.protocol === protocol.protocol;
        return `
          <button type="button"
                  class="llm-protocol-card${isSelected ? " is-selected" : ""}${isActive ? " is-active" : ""}"
                  data-llm-protocol="${escapeHtml(protocol.protocol)}"
                  data-provider-accent="${escapeHtml(protocol.accent)}">
            <span class="llm-provider-mark">${escapeHtml(protocol.mark)}</span>
            <span class="llm-protocol-copy">
              <strong>${escapeHtml(protocol.label)}</strong>
              <span>${escapeHtml(protocol.summary)}</span>
            </span>
            <span class="llm-protocol-count">${escapeHtml(`${protocolServices.length} 项服务${isActive ? " / 已激活" : ""}`)}</span>
          </button>
        `;
      })
      .join("");

    syncLlmEditorDraftUi(settings);

    elements.llmServiceId.value = draft.serviceId;
    elements.llmServiceName.value = draft.name;
    elements.llmServiceIcon.value = normalizeLlmIconValue(draft.icon);
    elements.llmServiceEndpoint.value = draft.endpoint;
    elements.llmServiceApiKey.value = draft.apiKey;
    elements.llmServiceApiKeyHelp.textContent = draft.apiKeySaved
      ? `当前已保存：${draft.apiKeyMasked || "已脱敏显示"}。留空表示继续使用当前 Key；输入新值会覆盖它。`
      : "保存后会持久化到后端，优先覆盖环境变量。";
    elements.llmActiveModel.innerHTML = draft.modelOptions.length
      ? draft.modelOptions
        .map(
          (model) => `<option value="${escapeHtml(model)}"${model === draft.model ? " selected" : ""}>${escapeHtml(model)}</option>`,
        )
        .join("")
      : '<option value="">先获取模型列表</option>';
    elements.llmActiveModel.disabled = !draft.modelOptions.length;
    if (draft.modelOptions.length) {
      elements.llmActiveModel.value = draft.model || draft.modelOptions[0];
    }
    elements.llmModelHelp.textContent = draft.modelOptions.length
      ? `当前已同步 ${draft.modelOptions.length} 个模型。`
      : "保存服务后，可通过接口拉取这项服务当前可用的模型。";
    elements.llmServiceDelete.hidden = !draft.serviceId;
    renderLlmIconPreview(draft);

    elements.llmServiceList.innerHTML = services.length
      ? services
        .map((service) => {
          const serviceProtocol = getLlmProtocolMeta(service.protocol, settings);
          const currentModel = state.llmServiceModelSelections[service.service_id]
            || service.active_model
            || service.model_options[0]
            || "";
          const canActivate = Boolean(currentModel);
          const activateLabel = service.is_active ? "当前使用中" : "使用这项";
          const activateDisabled = service.is_active || !canActivate;
          return `
            <article class="llm-service-card${service.is_active ? " is-active" : ""}"
                     data-provider-accent="${escapeHtml(serviceProtocol.accent)}">
              ${service.is_active ? '<div class="llm-service-state">当前工作台正在使用这项服务</div>' : ""}
              <div class="llm-service-top">
                <div class="llm-service-identity">
                  ${renderLlmServiceAvatar(service.icon, service.name, serviceProtocol.mark)}
                  <div>
                    <strong>${escapeHtml(service.name)}</strong>
                    <div class="llm-service-badges">
                      <span class="mini-badge">${escapeHtml(serviceProtocol.label)}</span>
                      ${service.is_active ? '<span class="mini-badge llm-live-badge">当前激活</span>' : ""}
                    </div>
                  </div>
                </div>
                <div class="llm-service-card-actions">
                  <button type="button" class="btn btn-ghost" data-llm-edit-service="${escapeHtml(service.service_id)}">编辑</button>
                  <button type="button" class="btn btn-danger" data-llm-delete-service="${escapeHtml(service.service_id)}">删除</button>
                </div>
              </div>
              <div class="llm-service-note">${escapeHtml(service.endpoint)}</div>
              <div class="llm-service-meta">
                <span>${escapeHtml(service.uses_official_endpoint ? "官方地址" : "自定义地址")}</span>
                <span>${escapeHtml(service.api_key_saved ? `Key ${service.api_key_masked || "已保存"}` : "未保存 Key")}</span>
              </div>
              <label class="llm-service-model-field">
                <span>活跃模型</span>
                <select data-llm-service-model="${escapeHtml(service.service_id)}"${service.model_options.length ? "" : " disabled"}>
                  ${
                    service.model_options.length
                      ? service.model_options
                        .map(
                          (model) => `<option value="${escapeHtml(model)}"${model === currentModel ? " selected" : ""}>${escapeHtml(model)}</option>`,
                        )
                        .join("")
                      : '<option value="">先获取模型</option>'
                  }
                </select>
              </label>
              <div class="llm-service-actions">
                <button type="button" class="btn btn-outline" data-llm-discover-service="${escapeHtml(service.service_id)}">获取模型</button>
                <button type="button" class="btn btn-primary" data-llm-activate-service="${escapeHtml(service.service_id)}"${activateDisabled ? " disabled" : ""}>${escapeHtml(activateLabel)}</button>
              </div>
            </article>
          `;
        })
        .join("")
      : '<div class="empty-state">这里还没有保存的服务。先选择协议模板，再新增一项服务。</div>';

    renderLlmStatus(message, messageKind);
    setLlmModalOpen(state.llmModalOpen);
    syncActionAvailability();
  }

  function collectLlmServicePayload() {
    const draft = getSelectedLlmDraft();
    const serviceId = elements.llmServiceId.value.trim() || draft.serviceId || "";
    const name = elements.llmServiceName.value.trim();
    const icon = normalizeLlmIconValue(elements.llmServiceIcon.value) || normalizeLlmIconValue(draft.icon);
    const endpoint = elements.llmServiceEndpoint.value.trim();
    const apiKey = elements.llmServiceApiKey.value.trim();
    const model = elements.llmActiveModel.value || draft.model || "";

    if (!name) {
      throw new Error("请先填写服务名称。");
    }
    if (!endpoint) {
      throw new Error("请先填写服务地址。");
    }
    setLlmEditorDraft({
      ...draft,
      serviceId,
      name,
      icon,
      endpoint,
      apiKey,
      model,
    });
    return {
      service_id: serviceId || undefined,
      protocol: draft.protocol,
      name,
      icon: icon || undefined,
      endpoint,
      api_key: apiKey || undefined,
      model: model || undefined,
    };
  }

  async function reloadSettingsAfterLlmMutation(message, kind = "status-ok", options = {}) {
    const refreshedSettings = await loadSettings(state.apiKey);
    state.settingsPage = refreshedSettings;
    renderSettingsOptions(refreshedSettings);
    if (options.serviceId) {
      primeLlmEditorFromSettings(refreshedSettings, { serviceId: options.serviceId });
    } else if (options.protocol) {
      primeLlmEditorFromSettings(refreshedSettings, { protocol: options.protocol });
    }
    renderSettingsPage(refreshedSettings);
    renderLlmPage(message, kind);
    if (state.catalogPage) {
      renderOverview(state.catalogPage, refreshedSettings);
    }
    updateShellSignals();
    syncPanelGuards();
    renderOperationChain(state.activeOperation);
  }

  async function saveCurrentLlmService() {
    const mutation = await upsertLlmService(state.apiKey, collectLlmServicePayload());
    await reloadSettingsAfterLlmMutation(
      mutation.action === "created" ? "服务已保存。" : "服务已更新。",
      "status-ok",
      { serviceId: mutation.service_id },
    );
    return mutation.service_id;
  }

  async function discoverModelsForService(serviceId) {
    const result = await discoverLlmModels(state.apiKey, { service_id: serviceId });
    await reloadSettingsAfterLlmMutation(
      `已同步 ${result.models.length} 个模型。`,
      "status-ok",
      { serviceId: result.service_id },
    );
  }

  async function discoverModelsFromEditor() {
    const serviceId = await saveCurrentLlmService();
    await discoverModelsForService(serviceId);
  }

  async function activateSavedLlmService(serviceId) {
    const service = getLlmServiceById(serviceId);
    const model = state.llmServiceModelSelections[serviceId]
      || service?.active_model
      || service?.model_options?.[0]
      || "";
    if (!model) {
      throw new Error("请先为这项服务获取模型列表。");
    }
    const activation = await activateLlmService(state.apiKey, {
      service_id: serviceId,
      model,
    });
    await reloadSettingsAfterLlmMutation(
      "已切换到这项服务。",
      "status-ok",
      { serviceId: activation.service_id },
    );
  }

  async function deleteSavedLlmService(serviceId, { closeEditor = false } = {}) {
    const service = getLlmServiceById(serviceId);
    if (!service) {
      throw new Error("没有找到要删除的服务。");
    }
    const mutation = await deleteLlmService(state.apiKey, { service_id: serviceId });
    await reloadSettingsAfterLlmMutation(
      service.is_active ? "服务已删除，工作台已切回内建模式。" : "服务已删除。",
      "status-ok",
      { protocol: service.protocol },
    );
    if (closeEditor) {
      closeLlmEditor();
    }
    return mutation;
  }

  async function updateDraftIconFromFile(file) {
    const compressedIcon = await compressLlmServiceIconFile(file);
    elements.llmServiceIcon.value = compressedIcon;
    updateLlmEditorDraft({ icon: compressedIcon });
    syncLlmEditorDraftUi();
    renderLlmIconPreview();
    renderLlmStatus("图标图片已更新，点击“保存服务”后才会生效。", "status-warn");
    syncActionAvailability();
  }

  return {
    getLlmProtocolCatalog,
    getLlmProtocolMeta,
    getLlmServices,
    getLlmServiceById,
    getLlmActiveService,
    getLlmSelectedService,
    getLiveLlmSelection,
    buildLlmDraftForProtocol,
    buildLlmDraftFromService,
    buildSelectedLlmApplyRequest,
    setLlmEditorDraft,
    updateLlmEditorDraft,
    ensureLlmEditorDraft,
    primeLlmEditorFromSettings,
    getSelectedLlmDraft,
    isLlmEditorDraftDirty,
    syncLlmServiceSelections,
    syncLlmEditorDraftUi,
    renderLlmIconPreview,
    renderLlmStatus,
    renderLlmPage,
    renderLlmSettings: renderLlmPage,
    setLlmModalOpen,
    openLlmEditor,
    closeLlmEditor,
    confirmDeleteLlmService,
    collectLlmServicePayload,
    reloadSettingsAfterLlmMutation,
    saveCurrentLlmService,
    discoverModelsForService,
    discoverModelsFromEditor,
    activateSavedLlmService,
    deleteSavedLlmService,
    updateDraftIconFromFile,
  };
}
