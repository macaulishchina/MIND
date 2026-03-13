import {
  ACCESS_DEPTH_LABELS,
  ANSWER_MODE_LABELS,
  AUTH_MODE_LABELS,
  ENTRYPOINT_LABELS,
  GATE_ENTRY_LABELS,
  LLM_ICON_MAX_DIMENSION,
  LLM_ICON_TARGET_BYTES,
  OFFLINE_JOB_KIND_LABELS,
  OPERATION_CHAIN_STATUS_LABELS,
  OPERATION_CHAIN_STEP_STATUS_LABELS,
  PROVIDER_EXECUTION_LABELS,
  PROVIDER_FAMILY_LABELS,
  PROVIDER_STATUS_LABELS,
  RETRY_POLICY_LABELS,
  SETTING_LABELS,
  VIEWPORT_LABELS,
} from "./constants.js";

export function delay(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

export function isPositiveInteger(value) {
  const parsed = Number.parseInt(String(value), 10);
  return Number.isInteger(parsed) && parsed > 0;
}

export function formatDateTime(value) {
  try {
    return new Date(value).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return String(value);
  }
}

export function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function formatValue(value) {
  if (value === null || value === undefined) {
    return "暂无";
  }
  if (value instanceof Date) {
    return formatDateTime(value);
  }
  if (Array.isArray(value)) {
    return value.length ? value.map((item) => formatValue(item)).join(", ") : "无";
  }
  if (typeof value === "object") {
    const entries = Object.entries(value)
      .filter(([, item]) => item !== undefined && item !== null && item !== "")
      .map(([key, item]) => `${key}: ${formatValue(item)}`);
    return entries.length ? entries.join(" / ") : "未注明";
  }
  return String(value);
}

export function renderMetricList(items) {
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

export function localizeViewport(value) {
  return VIEWPORT_LABELS[value] || value;
}

export function localizeSettingKey(key) {
  return SETTING_LABELS[key] || key;
}

export function localizeAccessDepth(value) {
  return ACCESS_DEPTH_LABELS[value] || value;
}

export function localizeProviderFamily(value) {
  return PROVIDER_FAMILY_LABELS[value] || value || "未注明";
}

export function localizeAnswerMode(value) {
  return ANSWER_MODE_LABELS[value] || value || "未注明";
}

export function localizeAuthMode(value) {
  return AUTH_MODE_LABELS[value] || value || "未注明";
}

export function localizeProviderStatus(value) {
  return PROVIDER_STATUS_LABELS[value] || value || "未注明";
}

export function localizeProviderExecution(value) {
  return PROVIDER_EXECUTION_LABELS[value] || value || "未注明";
}

export function localizeRetryPolicy(value) {
  return RETRY_POLICY_LABELS[value] || value || "未注明";
}

export function localizeContentType(value) {
  return value || "未注明";
}

export function localizeEntrypoint(entrypoint) {
  return ENTRYPOINT_LABELS[entrypoint] || {
    title: entrypoint,
    mode: "可用",
    summary: "这里显示一个已启用的功能入口。",
  };
}

export function localizeGateEntry(entry) {
  return GATE_ENTRY_LABELS[entry.entry_id] || entry.title;
}

export function truncateText(value, maxLength = 72) {
  const text = String(value || "").trim();
  if (!text) {
    return "未填写";
  }
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`;
}

export function localizeOfflineJobKind(value) {
  return OFFLINE_JOB_KIND_LABELS[value] || value || "未注明";
}

export function localizeOperationChainStatus(value) {
  return OPERATION_CHAIN_STATUS_LABELS[value] || value || "未注明";
}

export function localizeOperationStepStatus(value) {
  return OPERATION_CHAIN_STEP_STATUS_LABELS[value] || value || "未注明";
}

export function getAnswerModeFromSettings(settings) {
  return settings?.provider?.provider_family && settings.provider.provider_family !== "deterministic"
    ? "llm"
    : "builtin";
}

export function isLlmImageIconValue(value) {
  const icon = String(value || "").trim();
  return Boolean(icon) && (
    icon.startsWith("data:image/")
    || /^https?:\/\//i.test(icon)
  );
}

export function normalizeLlmIconValue(value) {
  return isLlmImageIconValue(value) ? String(value).trim() : "";
}

export function buildLlmAvatar(label, fallback = "L") {
  const value = String(label || "").trim();
  if (!value) {
    return Array.from(String(fallback || "L"))[0]?.toUpperCase() || "L";
  }
  const words = value
    .split(/[\s/_-]+/)
    .map((item) => Array.from(item.trim())[0] || "")
    .filter(Boolean);
  if (words.length) {
    return words[0].toUpperCase();
  }
  return Array.from(value)[0]?.toUpperCase() || (Array.from(String(fallback || "L"))[0]?.toUpperCase() || "L");
}

export function renderLlmServiceAvatar(icon, label, fallback = "L") {
  const normalizedIcon = normalizeLlmIconValue(icon);
  if (normalizedIcon) {
    return `
      <span class="llm-service-avatar has-image">
        <img src="${escapeHtml(normalizedIcon)}" alt="${escapeHtml(`${label} 图标`)}" loading="lazy">
      </span>
    `;
  }
  return `<span class="llm-service-avatar">${escapeHtml(buildLlmAvatar(label, fallback))}</span>`;
}

export function estimateDataUrlBytes(dataUrl) {
  const payload = String(dataUrl || "").split(",")[1] || "";
  const padding = payload.endsWith("==") ? 2 : (payload.endsWith("=") ? 1 : 0);
  return Math.max(0, Math.floor((payload.length * 3) / 4) - padding);
}

export function loadImageElement(src) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("图标图片加载失败，请换一张图片试试。"));
    image.src = src;
  });
}

export async function compressLlmServiceIconFile(file) {
  if (!file || !String(file.type || "").startsWith("image/")) {
    throw new Error("请上传图片文件。");
  }

  const objectUrl = URL.createObjectURL(file);
  try {
    const image = await loadImageElement(objectUrl);
    let width = image.naturalWidth || image.width || LLM_ICON_MAX_DIMENSION;
    let height = image.naturalHeight || image.height || LLM_ICON_MAX_DIMENSION;
    const initialScale = Math.min(1, LLM_ICON_MAX_DIMENSION / Math.max(width, height));
    width = Math.max(48, Math.round(width * initialScale));
    height = Math.max(48, Math.round(height * initialScale));

    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");
    if (!context) {
      throw new Error("当前浏览器不支持图标压缩。");
    }

    let quality = 0.86;
    let dataUrl = "";
    for (let attempt = 0; attempt < 6; attempt += 1) {
      canvas.width = width;
      canvas.height = height;
      context.clearRect(0, 0, width, height);
      context.imageSmoothingEnabled = true;
      context.imageSmoothingQuality = "high";
      context.drawImage(image, 0, 0, width, height);
      dataUrl = canvas.toDataURL("image/webp", quality);
      if (estimateDataUrlBytes(dataUrl) <= LLM_ICON_TARGET_BYTES || (width <= 80 && height <= 80)) {
        break;
      }
      if (quality > 0.58) {
        quality -= 0.08;
      } else {
        width = Math.max(64, Math.round(width * 0.84));
        height = Math.max(64, Math.round(height * 0.84));
        quality = 0.82;
      }
    }
    return dataUrl;
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}
