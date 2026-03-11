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

const elements = {
  authForm: document.querySelector("#auth-form"),
  apiKey: document.querySelector("#api-key"),
  authStatus: document.querySelector("#auth-status"),
  clearKey: document.querySelector("#clear-key"),
  reloadOverview: document.querySelector("#reload-overview"),
  overviewGrid: document.querySelector("#overview-grid"),
  loadGateDemo: document.querySelector("#load-gate-demo"),
  gateDemoResult: document.querySelector("#gate-demo-result"),
  ingestForm: document.querySelector("#ingest-form"),
  ingestContent: document.querySelector("#ingest-content"),
  ingestEpisodeId: document.querySelector("#ingest-episode-id"),
  ingestTimestampOrder: document.querySelector("#ingest-timestamp-order"),
  ingestReset: document.querySelector("#ingest-reset"),
  ingestResult: document.querySelector("#ingest-result"),
  retrieveForm: document.querySelector("#retrieve-form"),
  retrieveQuery: document.querySelector("#retrieve-query"),
  retrieveEpisodeId: document.querySelector("#retrieve-episode-id"),
  retrieveMaxCandidates: document.querySelector("#retrieve-max-candidates"),
  retrieveReset: document.querySelector("#retrieve-reset"),
  retrieveResult: document.querySelector("#retrieve-result"),
  accessForm: document.querySelector("#access-form"),
  accessQuery: document.querySelector("#access-query"),
  accessDepth: document.querySelector("#access-depth"),
  accessEpisodeId: document.querySelector("#access-episode-id"),
  accessTaskId: document.querySelector("#access-task-id"),
  accessExplain: document.querySelector("#access-explain"),
  accessReset: document.querySelector("#access-reset"),
  accessResult: document.querySelector("#access-result"),
  offlineForm: document.querySelector("#offline-form"),
  offlineJobKind: document.querySelector("#offline-job-kind"),
  offlineEpisodeId: document.querySelector("#offline-episode-id"),
  offlineFocus: document.querySelector("#offline-focus"),
  offlineTargetRefs: document.querySelector("#offline-target-refs"),
  offlineReason: document.querySelector("#offline-reason"),
  offlinePriority: document.querySelector("#offline-priority"),
  offlineReset: document.querySelector("#offline-reset"),
  offlineResult: document.querySelector("#offline-result"),
  settingsForm: document.querySelector("#settings-form"),
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
  debugRunId: document.querySelector("#debug-run-id"),
  debugOperationId: document.querySelector("#debug-operation-id"),
  debugObjectId: document.querySelector("#debug-object-id"),
  debugLimit: document.querySelector("#debug-limit"),
  debugReset: document.querySelector("#debug-reset"),
  debugResult: document.querySelector("#debug-result"),
};

const state = {
  apiKey: window.localStorage.getItem(STORAGE_KEY) || "",
  settingsPage: null,
};

function setStatus(message) {
  elements.authStatus.textContent = message;
}

function renderOverview(catalog, settings) {
  const experienceCards = (catalog.entries || [])
    .map(
      (entry) => `
        <article class="overview-card">
          <h3>${escapeHtml(entry.title)}</h3>
          <p class="meta">${escapeHtml(entry.summary)}</p>
          <ul class="pill-row">
            ${(entry.supported_viewports || [])
              .map((viewport) => `<li>${escapeHtml(viewport)}</li>`)
              .join("")}
          </ul>
        </article>
      `,
    )
    .join("");

  elements.overviewGrid.innerHTML = `
    <article class="overview-card">
      <h3>Runtime</h3>
      <p class="meta">backend=${escapeHtml(settings.runtime.backend)} profile=${escapeHtml(settings.runtime.profile)}</p>
      <ul class="pill-row">
        <li>${escapeHtml(settings.provider.provider)}</li>
        <li>${escapeHtml(settings.provider.model)}</li>
        <li>${settings.runtime.dev_mode ? "dev_mode=true" : "dev_mode=false"}</li>
      </ul>
    </article>
    ${experienceCards}
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
      ${currentSnapshot ? "Applied snapshot available" : "No applied snapshot yet"}
    </div>
    <div class="result-grid">
      <div class="result-block">
        <h3>Runtime</h3>
        <ul class="notes-list">
          <li>backend=${escapeHtml(settings.runtime.backend)}</li>
          <li>profile=${escapeHtml(settings.runtime.profile)}</li>
          <li>provider=${escapeHtml(settings.provider.provider)}</li>
          <li>model=${escapeHtml(settings.provider.model)}</li>
          <li>${settings.runtime.dev_mode ? "dev_mode=true" : "dev_mode=false"}</li>
        </ul>
      </div>
      <div class="result-block">
        <h3>Current Snapshot</h3>
        ${renderSettingsSnapshot(currentSnapshot, "No applied snapshot persisted.")}
      </div>
      <div class="result-block">
        <h3>Previous Snapshot</h3>
        ${renderSettingsSnapshot(previousSnapshot, "No previous snapshot available.")}
      </div>
    </div>
  `;
}

function renderSettingsPreview(preview) {
  const changes = preview.changes || [];
  const envOverrides = Object.entries(preview.applied_env_overrides || {});
  elements.settingsResult.innerHTML = `
    <div class="status ${changes.length ? "status-ok" : "status-warn"}">
      ${changes.length ? `${changes.length} changed keys` : "No effective change"}
    </div>
    <ul class="change-list">
      ${changes
        .map(
          (change) => `
            <li>
              <strong>${escapeHtml(change.key)}</strong>
              <span>${escapeHtml(String(change.before))} -> ${escapeHtml(String(change.after))}</span>
            </li>
          `,
        )
        .join("") || "<li><span>Preview matches current settings.</span></li>"}
    </ul>
    <ul class="notes-list">
      ${envOverrides
        .map(([key, value]) => `<li>${escapeHtml(key)}=${escapeHtml(value)}</li>`)
        .join("") || "<li>No environment overrides required.</li>"}
    </ul>
  `;
}

function renderSettingsMutation(result) {
  const preview = result.preview || {};
  const currentSnapshot = result.current_snapshot;
  const previousSnapshot = result.previous_snapshot;
  const envOverrides = Object.entries(
    currentSnapshot?.applied_env_overrides || {},
  );
  elements.settingsResult.innerHTML = `
    <div class="status status-ok">
      ${escapeHtml(result.action)} saved as ${escapeHtml(currentSnapshot.snapshot_id)}
    </div>
    <div class="result-grid">
      <div class="result-block">
        <h3>Saved Snapshot</h3>
        ${renderSettingsSnapshot(currentSnapshot, "No saved snapshot.")}
      </div>
      <div class="result-block">
        <h3>Previous Snapshot</h3>
        ${renderSettingsSnapshot(previousSnapshot, "No previous snapshot available.")}
      </div>
      <div class="result-block">
        <h3>Restart Instructions</h3>
        <ul class="notes-list">
          <li>${preview.restart_required ? "Restart required to activate this config." : "No restart required."}</li>
          ${envOverrides
            .map(([key, value]) => `<li>${escapeHtml(key)}=${escapeHtml(value)}</li>`)
            .join("") || "<li>No environment overrides required.</li>"}
        </ul>
      </div>
    </div>
  `;
}

function renderGateDemo(page) {
  const entries = page.entries || [];
  elements.gateDemoResult.innerHTML = `
    <div class="status ${entries.length ? "status-ok" : "status-warn"}">
      ${escapeHtml(page.page_version || "gate-demo")} / ${entries.length} entries
    </div>
    <div class="result-grid">
      <div class="result-block">
        <h3>Summary Surface</h3>
        <ul class="stack-list">
          ${entries
            .map(
              (entry) => `
                <li>
                  <strong>${escapeHtml(entry.title)}</strong>
                  <div class="meta">${escapeHtml(entry.kind)} / ${escapeHtml((entry.supported_viewports || []).join(", "))}</div>
                  <div>${escapeHtml(entry.summary)}</div>
                </li>
              `,
            )
            .join("") || "<li>No gate/demo summaries returned.</li>"}
        </ul>
      </div>
    </div>
  `;
}

function renderIngestResult(result) {
  elements.ingestResult.innerHTML = `
    <div class="status status-ok">Stored ${escapeHtml(result.object_id)}</div>
    <div class="result-grid">
      <div class="result-block">
        <h3>Object</h3>
        <ul class="notes-list">
          <li>version=${escapeHtml(result.version)}</li>
          <li>provenance=${escapeHtml(result.provenance_id || "n/a")}</li>
          <li>trace_ref=${escapeHtml(result.trace_ref || "n/a")}</li>
        </ul>
      </div>
    </div>
  `;
}

function renderRetrieveResult(result) {
  const candidates = result.candidates || [];
  elements.retrieveResult.innerHTML = `
    <div class="status ${candidates.length ? "status-ok" : "status-warn"}">
      ${escapeHtml(result.candidate_count)} candidates
    </div>
    <div class="result-grid">
      <div class="result-block">
        <h3>Evidence Summary</h3>
        <p>${escapeHtml(formatValue(result.evidence_summary || "none"))}</p>
      </div>
      <div class="result-block">
        <h3>Candidates</h3>
        <ul class="stack-list">
          ${candidates
            .map(
              (candidate) => `
                <li>
                  <strong>${escapeHtml(candidate.object_id)}</strong>
                  <div class="meta">${escapeHtml(candidate.object_type)} score=${escapeHtml(candidate.score ?? "n/a")}</div>
                  <div>${escapeHtml(candidate.content_preview || "no preview")}</div>
                </li>
              `,
            )
            .join("") || "<li>No candidates returned.</li>"}
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
      depth=${escapeHtml(result.resolved_depth)} context=${escapeHtml(result.context_kind)}
    </div>
    <div class="result-grid">
      <div class="result-block">
        <h3>Summary</h3>
        <ul class="notes-list">
          <li>${escapeHtml(result.summary)}</li>
          <li>context_objects=${escapeHtml(result.context_object_count)}</li>
          <li>candidate_count=${escapeHtml(result.candidate_count)}</li>
          <li>selected_count=${escapeHtml(result.selected_count)}</li>
          <li>trace_ref=${escapeHtml(result.trace_ref || "n/a")}</li>
        </ul>
      </div>
      <div class="result-block">
        <h3>Candidate Objects</h3>
        <ul class="stack-list">
          ${candidateObjects
            .map(
              (item) => `
                <li>
                  <strong>${escapeHtml(item.object_id)}</strong>
                  <div class="meta">${escapeHtml(item.object_type)} episode=${escapeHtml(item.episode_id || "n/a")}</div>
                  <div>${escapeHtml(item.preview || "no preview")}</div>
                </li>
              `,
            )
            .join("") || "<li>No candidate objects returned.</li>"}
        </ul>
      </div>
      <div class="result-block">
        <h3>Selected Objects</h3>
        <ul class="stack-list">
          ${selectedObjects
            .map(
              (item) => `
                <li>
                  <strong>${escapeHtml(item.object_id)}</strong>
                  <div class="meta">${escapeHtml(item.object_type)} episode=${escapeHtml(item.episode_id || "n/a")}</div>
                  <div>${escapeHtml(item.preview || "no preview")}</div>
                </li>
              `,
            )
            .join("") || "<li>No selected objects returned.</li>"}
        </ul>
      </div>
    </div>
  `;
}

function renderOfflineResult(result) {
  elements.offlineResult.innerHTML = `
    <div class="status status-ok">Submitted ${escapeHtml(result.job_id)}</div>
    <ul class="notes-list">
      <li>status=${escapeHtml(result.status)}</li>
    </ul>
  `;
}

function renderDebugTimeline(result) {
  const timeline = result.timeline || [];
  const deltas = result.object_deltas || [];
  const contextViews = result.context_views || [];
  const evidenceViews = result.evidence_views || [];
  elements.debugResult.innerHTML = `
    <div class="status ${timeline.length ? "status-ok" : "status-warn"}">
      ${timeline.length} timeline events
    </div>
    <div class="timeline-list">
      ${timeline
        .map(
          (event) => `
            <article class="event-card">
              <h3>${escapeHtml(event.label)}</h3>
              <p class="meta">${escapeHtml(event.scope)} / ${escapeHtml(event.kind)}</p>
              <p>${escapeHtml(event.summary)}</p>
              <p class="meta">${escapeHtml(event.occurred_at)}</p>
            </article>
          `,
        )
        .join("") || '<div class="empty-state">No timeline events returned.</div>'}
    </div>
    <div class="result-panel">
      <h3>Object Deltas</h3>
      <ul class="notes-list">
        ${deltas
          .map(
            (delta) => `
              <li>${escapeHtml(delta.object_id)} v${delta.object_version} - ${escapeHtml(delta.summary)}</li>
            `,
          )
        .join("") || "<li>No object deltas in this selection.</li>"}
      </ul>
    </div>
    <div class="result-panel">
      <h3>Context Selection</h3>
      <ul class="stack-list">
        ${contextViews
          .map(
            (view) => `
              <li>
                <strong>${escapeHtml(view.context_kind)}</strong>
                <div class="meta">${escapeHtml(view.operation_id)} / ${escapeHtml(view.workspace_id || "no-workspace")}</div>
                <div>${escapeHtml(view.summary)}</div>
                <div class="meta">context=${escapeHtml((view.context_object_ids || []).join(", ") || "none")}</div>
                <div class="meta">selected=${escapeHtml((view.selected_object_ids || []).join(", ") || "none")}</div>
              </li>
            `,
          )
          .join("") || "<li>No context selections in this selection.</li>"}
      </ul>
    </div>
    <div class="result-panel">
      <h3>Evidence Support</h3>
      <ul class="stack-list">
        ${evidenceViews
          .map(
            (view) => `
              <li>
                <strong>${escapeHtml(view.object_id)}</strong>
                <div class="meta">${escapeHtml(view.object_type || "unknown")} / ${view.selected ? "selected" : "candidate"}</div>
                <div>${escapeHtml(view.summary)}</div>
                <div class="meta">score=${escapeHtml(view.score ?? "n/a")} priority=${escapeHtml(view.priority ?? "n/a")}</div>
                <div class="meta">evidence_refs=${escapeHtml((view.evidence_refs || []).join(", ") || "none")}</div>
              </li>
            `,
          )
          .join("") || "<li>No evidence support in this selection.</li>"}
      </ul>
    </div>
  `;
}

async function refreshOverview() {
  if (!state.apiKey) {
    elements.overviewGrid.innerHTML =
      '<div class="empty-state">Save an API key to load catalog and runtime settings.</div>';
    return;
  }
  const [catalog, settings] = await Promise.all([
    loadCatalog(state.apiKey),
    loadSettings(state.apiKey),
  ]);
  state.settingsPage = settings;
  renderOverview(catalog, settings);
  renderSettingsOptions(settings);
  renderSettingsPage(settings);
}

async function refreshGateDemo() {
  if (!state.apiKey) {
    elements.gateDemoResult.innerHTML =
      '<div class="empty-state">Save an API key to load gate and demo summaries.</div>';
    return;
  }
  const page = await loadGateDemo(state.apiKey);
  renderGateDemo(page);
}

function collectIngestRequest() {
  const content = elements.ingestContent.value.trim();
  if (!content) {
    throw new Error("Content is required");
  }
  const body = {
    content,
    timestamp_order: Number.parseInt(elements.ingestTimestampOrder.value, 10) || 1,
  };
  if (elements.ingestEpisodeId.value.trim()) {
    body.episode_id = elements.ingestEpisodeId.value.trim();
  }
  return body;
}

function collectRetrieveRequest() {
  const query = elements.retrieveQuery.value.trim();
  if (!query) {
    throw new Error("Query is required");
  }
  const body = {
    query,
    max_candidates: Number.parseInt(elements.retrieveMaxCandidates.value, 10) || 10,
  };
  if (elements.retrieveEpisodeId.value.trim()) {
    body.episode_id = elements.retrieveEpisodeId.value.trim();
  }
  return body;
}

function collectAccessRequest() {
  const query = elements.accessQuery.value.trim();
  if (!query) {
    throw new Error("Query is required");
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
      throw new Error("episode_id is required for reflect_episode");
    }
    body.payload = {
      episode_id: episodeId,
      focus: focus || "frontend reflection request",
    };
    return body;
  }

  const targetRefs = elements.offlineTargetRefs.value
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const reason = elements.offlineReason.value.trim();
  if (targetRefs.length < 2) {
    throw new Error("promote_schema requires at least two target refs");
  }
  if (!reason) {
    throw new Error("reason is required for promote_schema");
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

function fillSelect(select, values) {
  const current = select.value;
  const options = ['<option value="">no change</option>']
    .concat(
      (values || []).map(
        (value) =>
          `<option value="${escapeHtml(value)}"${value === current ? " selected" : ""}>${escapeHtml(value)}</option>`,
      ),
    )
    .join("");
  select.innerHTML = options;
}

function resetIngestForm() {
  elements.ingestForm.reset();
  elements.ingestTimestampOrder.value = "1";
  elements.ingestResult.innerHTML = '<div class="empty-state">No ingest run yet.</div>';
}

function resetRetrieveForm() {
  elements.retrieveForm.reset();
  elements.retrieveMaxCandidates.value = "10";
  elements.retrieveResult.innerHTML = '<div class="empty-state">No retrieval run yet.</div>';
}

function resetAccessForm() {
  elements.accessForm.reset();
  elements.accessDepth.value = "auto";
  elements.accessResult.innerHTML = '<div class="empty-state">No access run yet.</div>';
}

function resetOfflineForm() {
  elements.offlineForm.reset();
  elements.offlineJobKind.value = "reflect_episode";
  elements.offlinePriority.value = "0.5";
  elements.offlineResult.innerHTML = '<div class="empty-state">No offline submission yet.</div>';
}

function resetSettingsForm() {
  elements.settingsForm.reset();
  elements.settingsResult.innerHTML = state.settingsPage
    ? ""
    : '<div class="empty-state">No preview loaded.</div>';
  if (state.settingsPage) {
    renderSettingsPage(state.settingsPage);
  }
}

function resetGateDemo() {
  elements.gateDemoResult.innerHTML =
    '<div class="empty-state">No gate or demo summary loaded.</div>';
}

function resetDebugForm() {
  elements.debugForm.reset();
  elements.debugLimit.value = "80";
  elements.debugResult.innerHTML = '<div class="empty-state">No debug query loaded.</div>';
}

function formatValue(value) {
  if (value === null || value === undefined) {
    return "n/a";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderSettingsSnapshot(snapshot, emptyMessage) {
  if (!snapshot) {
    return `<div class="empty-state">${escapeHtml(emptyMessage)}</div>`;
  }
  const request = snapshot.request || {};
  const envOverrides = Object.entries(snapshot.applied_env_overrides || {});
  return `
    <ul class="notes-list">
      <li>snapshot=${escapeHtml(snapshot.snapshot_id)}</li>
      <li>action=${escapeHtml(snapshot.action)}</li>
      <li>request=${escapeHtml(JSON.stringify(request))}</li>
      <li>changed_keys=${escapeHtml((snapshot.changed_keys || []).join(", ") || "none")}</li>
      ${envOverrides
        .map(([key, value]) => `<li>${escapeHtml(key)}=${escapeHtml(value)}</li>`)
        .join("") || "<li>No environment overrides required.</li>"}
    </ul>
  `;
}

async function withStatus(work) {
  try {
    setStatus(state.apiKey ? "Working..." : "No API key stored.");
    await work();
    setStatus(state.apiKey ? "Ready." : "No API key stored.");
  } catch (error) {
    setStatus(error instanceof Error ? error.message : "Unexpected frontend error");
  }
}

elements.authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  state.apiKey = elements.apiKey.value.trim();
  if (state.apiKey) {
    window.localStorage.setItem(STORAGE_KEY, state.apiKey);
    await withStatus(refreshOverview);
  } else {
    window.localStorage.removeItem(STORAGE_KEY);
    setStatus("No API key stored.");
  }
});

elements.clearKey.addEventListener("click", () => {
  state.apiKey = "";
  elements.apiKey.value = "";
  window.localStorage.removeItem(STORAGE_KEY);
  resetIngestForm();
  resetRetrieveForm();
  resetAccessForm();
  resetOfflineForm();
  resetSettingsForm();
  resetGateDemo();
  resetDebugForm();
  void refreshOverview();
  setStatus("No API key stored.");
});

elements.reloadOverview.addEventListener("click", () => {
  void withStatus(refreshOverview);
});

elements.loadGateDemo.addEventListener("click", () => {
  void withStatus(refreshGateDemo);
});

elements.ingestForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await withStatus(async () => {
    const result = await submitIngest(state.apiKey, collectIngestRequest());
    renderIngestResult(result);
  });
});

elements.ingestReset.addEventListener("click", resetIngestForm);

elements.retrieveForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await withStatus(async () => {
    const result = await submitRetrieve(state.apiKey, collectRetrieveRequest());
    renderRetrieveResult(result);
  });
});

elements.retrieveReset.addEventListener("click", resetRetrieveForm);

elements.accessForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await withStatus(async () => {
    const result = await submitAccess(state.apiKey, collectAccessRequest());
    renderAccessResult(result);
  });
});

elements.accessReset.addEventListener("click", resetAccessForm);

elements.offlineForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await withStatus(async () => {
    const result = await submitOffline(state.apiKey, collectOfflineRequest());
    renderOfflineResult(result);
  });
});

elements.offlineReset.addEventListener("click", resetOfflineForm);

elements.settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await withStatus(async () => {
    const body = collectSettingsPreviewRequest();
    if (!Object.keys(body).length) {
      throw new Error("Pick at least one settings field to preview");
    }
    const result = await previewSettings(state.apiKey, body);
    renderSettingsPreview(result);
  });
});

elements.settingsApply.addEventListener("click", async () => {
  await withStatus(async () => {
    const body = collectSettingsPreviewRequest();
    if (!Object.keys(body).length) {
      throw new Error("Pick at least one settings field to apply");
    }
    const result = await applySettings(state.apiKey, body);
    const refreshedSettings = await loadSettings(state.apiKey);
    state.settingsPage = refreshedSettings;
    renderSettingsOptions(refreshedSettings);
    renderSettingsMutation(result);
  });
});

elements.settingsRestore.addEventListener("click", async () => {
  await withStatus(async () => {
    const result = await restoreSettings(state.apiKey);
    const refreshedSettings = await loadSettings(state.apiKey);
    state.settingsPage = refreshedSettings;
    renderSettingsOptions(refreshedSettings);
    renderSettingsMutation(result);
  });
});

elements.settingsReset.addEventListener("click", resetSettingsForm);

elements.debugForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await withStatus(async () => {
    const body = collectDebugRequest();
    if (!body.run_id && !body.operation_id && !body.object_id) {
      throw new Error("Provide run_id, operation_id, or object_id");
    }
    const result = await loadDebugTimeline(state.apiKey, body);
    renderDebugTimeline(result);
  });
});

elements.debugReset.addEventListener("click", resetDebugForm);

elements.apiKey.value = state.apiKey;
setStatus(state.apiKey ? "Ready." : "No API key stored.");
void refreshOverview();
