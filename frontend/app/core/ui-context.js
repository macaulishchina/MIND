import { DEFAULTS, UI_CONTEXT_KEY } from "../constants.js";

const HASH_KEYS = {
  workspace: "workspace",
  operation: "operation",
  settings: "settings",
};

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

export function parseWorkbenchHash(hash, defaults = DEFAULTS) {
  const raw = typeof hash === "string" ? hash.trim() : "";
  if (!raw.startsWith("#") || raw.length <= 1) {
    return {
      activeWorkspace: defaults.workspace,
      activeOperation: defaults.operation,
      activeSettingsSection: defaults.settingsSection,
    };
  }

  const params = new URLSearchParams(raw.slice(1));
  return {
    activeWorkspace: params.get(HASH_KEYS.workspace) || defaults.workspace,
    activeOperation: params.get(HASH_KEYS.operation) || defaults.operation,
    activeSettingsSection: params.get(HASH_KEYS.settings) || defaults.settingsSection,
  };
}

export function serializeWorkbenchHash(context, defaults = DEFAULTS) {
  const params = new URLSearchParams();
  const workspace = context?.activeWorkspace || defaults.workspace;
  const operation = context?.activeOperation || defaults.operation;
  const settings = context?.activeSettingsSection || defaults.settingsSection;

  params.set(HASH_KEYS.workspace, workspace);
  if (workspace === "workspace-operations") {
    params.set(HASH_KEYS.operation, operation);
  }
  if (workspace === "workspace-settings") {
    params.set(HASH_KEYS.settings, settings);
  }
  return `#${params.toString()}`;
}

export function loadWorkbenchContext(storage, defaults = DEFAULTS) {
  try {
    const raw = storage?.getItem(UI_CONTEXT_KEY);
    if (!raw) {
      return {
        activeWorkspace: defaults.workspace,
        activeOperation: defaults.operation,
        activeSettingsSection: defaults.settingsSection,
      };
    }
    const parsed = JSON.parse(raw);
    return {
      activeWorkspace: isNonEmptyString(parsed?.activeWorkspace)
        ? parsed.activeWorkspace
        : defaults.workspace,
      activeOperation: isNonEmptyString(parsed?.activeOperation)
        ? parsed.activeOperation
        : defaults.operation,
      activeSettingsSection: isNonEmptyString(parsed?.activeSettingsSection)
        ? parsed.activeSettingsSection
        : defaults.settingsSection,
    };
  } catch {
    return {
      activeWorkspace: defaults.workspace,
      activeOperation: defaults.operation,
      activeSettingsSection: defaults.settingsSection,
    };
  }
}

export function normalizeWorkbenchContext(
  context,
  {
    workspaceIds = [],
    operationIds = [],
    settingsSectionIds = [],
  } = {},
  defaults = DEFAULTS,
) {
  const workspace = workspaceIds.includes(context?.activeWorkspace)
    ? context.activeWorkspace
    : defaults.workspace;
  const operation = operationIds.includes(context?.activeOperation)
    ? context.activeOperation
    : defaults.operation;
  const settingsSection = settingsSectionIds.includes(context?.activeSettingsSection)
    ? context.activeSettingsSection
    : defaults.settingsSection;
  return {
    activeWorkspace: workspace,
    activeOperation: operation,
    activeSettingsSection: settingsSection,
  };
}

export function resolveInitialWorkbenchContext(
  hash,
  storage,
  validIds,
  defaults = DEFAULTS,
) {
  const hashContext = normalizeWorkbenchContext(parseWorkbenchHash(hash, defaults), validIds, defaults);
  const persistedContext = normalizeWorkbenchContext(
    loadWorkbenchContext(storage, defaults),
    validIds,
    defaults,
  );
  return hash && hash.trim().startsWith("#") && hash.trim().length > 1
    ? hashContext
    : persistedContext;
}

export function persistWorkbenchContext(storage, context, defaults = DEFAULTS) {
  try {
    storage?.setItem(
      UI_CONTEXT_KEY,
      JSON.stringify({
        activeWorkspace: context?.activeWorkspace || defaults.workspace,
        activeOperation: context?.activeOperation || defaults.operation,
        activeSettingsSection: context?.activeSettingsSection || defaults.settingsSection,
      }),
    );
  } catch {
    // Local storage failures should never block the workbench.
  }
}
