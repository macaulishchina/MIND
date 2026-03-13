import { DEFAULTS } from "../constants.js";
import {
  normalizeWorkbenchContext,
  parseWorkbenchHash,
  persistWorkbenchContext,
  resolveInitialWorkbenchContext,
  serializeWorkbenchHash,
} from "./ui-context.js";

export function createWorkbenchRouter({
  windowRef = window,
  storage = window.localStorage,
  elements,
  state,
  defaults = DEFAULTS,
  renderOperationChain,
  setOperationChainDrawerOpen,
}) {
  const validIds = {
    workspaceIds: elements.workspacePanels.map((panel) => panel.id),
    operationIds: elements.operationPanels.map((panel) => panel.id),
    settingsSectionIds: elements.settingsPanels.map((panel) => panel.id),
  };

  let isApplyingHash = false;

  function persistRoute() {
    persistWorkbenchContext(
      storage,
      {
        activeWorkspace: state.activeWorkspace,
        activeOperation: state.activeOperation,
        activeSettingsSection: state.activeSettingsSection,
      },
      defaults,
    );
  }

  function syncHash({ replace = false } = {}) {
    const nextHash = serializeWorkbenchHash(
      {
        activeWorkspace: state.activeWorkspace,
        activeOperation: state.activeOperation,
        activeSettingsSection: state.activeSettingsSection,
      },
      defaults,
    );
    if (windowRef.location.hash === nextHash) {
      return;
    }
    if (replace) {
      windowRef.history.replaceState(null, "", nextHash);
      return;
    }
    windowRef.location.hash = nextHash;
  }

  function applyWorkspace(targetId) {
    state.activeWorkspace = targetId;
    if (targetId !== "workspace-operations") {
      setOperationChainDrawerOpen(false);
    }
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

  function applyOperation(targetId) {
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
    renderOperationChain(targetId);
  }

  function applySettingsSection(targetId) {
    state.activeSettingsSection = targetId;
    elements.settingsTabs.forEach((tab) => {
      const active = tab.dataset.settingsTarget === targetId;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    elements.settingsPanels.forEach((panel) => {
      const active = panel.id === targetId;
      panel.classList.toggle("is-active", active);
      panel.setAttribute("aria-hidden", active ? "false" : "true");
    });
  }

  function applyRoute(context, { sync = true, replace = false, persist = true } = {}) {
    const normalized = normalizeWorkbenchContext(context, validIds, defaults);
    applyWorkspace(normalized.activeWorkspace);
    applyOperation(normalized.activeOperation);
    applySettingsSection(normalized.activeSettingsSection);
    if (persist) {
      persistRoute();
    }
    if (sync) {
      syncHash({ replace });
    }
  }

  function navigate(nextContext, options = {}) {
    applyRoute(
      {
        activeWorkspace: nextContext.activeWorkspace ?? state.activeWorkspace,
        activeOperation: nextContext.activeOperation ?? state.activeOperation,
        activeSettingsSection: nextContext.activeSettingsSection ?? state.activeSettingsSection,
      },
      options,
    );
  }

  function setActiveWorkspace(targetId, options = {}) {
    navigate({ activeWorkspace: targetId }, options);
  }

  function setActiveOperation(targetId, options = {}) {
    navigate(
      {
        activeWorkspace: "workspace-operations",
        activeOperation: targetId,
      },
      options,
    );
  }

  function setActiveSettingsSection(targetId, options = {}) {
    navigate(
      {
        activeWorkspace: "workspace-settings",
        activeSettingsSection: targetId,
      },
      options,
    );
  }

  function applyHashRoute() {
    if (isApplyingHash) {
      return;
    }
    isApplyingHash = true;
    try {
      const route = normalizeWorkbenchContext(
        parseWorkbenchHash(windowRef.location.hash, defaults),
        validIds,
        defaults,
      );
      applyRoute(route, { sync: false, persist: true });
    } finally {
      isApplyingHash = false;
    }
  }

  function initialize() {
    const initialContext = resolveInitialWorkbenchContext(
      windowRef.location.hash,
      storage,
      validIds,
      defaults,
    );
    applyRoute(initialContext, { sync: true, replace: true, persist: true });
    windowRef.addEventListener("hashchange", applyHashRoute);
  }

  return {
    initialize,
    navigate,
    setActiveWorkspace,
    setActiveOperation,
    setActiveSettingsSection,
    getCurrentRoute() {
      return {
        activeWorkspace: state.activeWorkspace,
        activeOperation: state.activeOperation,
        activeSettingsSection: state.activeSettingsSection,
      };
    },
  };
}
