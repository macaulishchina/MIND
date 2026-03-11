const JSON_HEADERS = {
  "Content-Type": "application/json",
};

function authHeaders(apiKey) {
  if (!apiKey) {
    throw new Error("API key required");
  }
  return {
    ...JSON_HEADERS,
    "X-API-Key": apiKey,
  };
}

async function fetchJson(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = payload?.error?.message || payload?.detail || `HTTP ${response.status}`;
    throw new Error(message);
  }
  if (payload.status && payload.status !== "ok") {
    const message = payload?.error?.message || `App status ${payload.status}`;
    throw new Error(message);
  }
  return payload.result ?? payload;
}

export async function loadCatalog(apiKey) {
  return fetchJson("/v1/frontend/catalog", {
    headers: authHeaders(apiKey),
  });
}

export async function loadGateDemo(apiKey) {
  return fetchJson("/v1/frontend/gate-demo", {
    headers: authHeaders(apiKey),
  });
}

export async function submitIngest(apiKey, body) {
  return fetchJson("/v1/frontend/ingest", {
    method: "POST",
    headers: authHeaders(apiKey),
    body: JSON.stringify(body),
  });
}

export async function submitRetrieve(apiKey, body) {
  return fetchJson("/v1/frontend/retrieve", {
    method: "POST",
    headers: authHeaders(apiKey),
    body: JSON.stringify(body),
  });
}

export async function submitAccess(apiKey, body) {
  return fetchJson("/v1/frontend/access", {
    method: "POST",
    headers: authHeaders(apiKey),
    body: JSON.stringify(body),
  });
}

export async function submitOffline(apiKey, body) {
  return fetchJson("/v1/frontend/offline", {
    method: "POST",
    headers: authHeaders(apiKey),
    body: JSON.stringify(body),
  });
}

export async function loadSettings(apiKey) {
  return fetchJson("/v1/frontend/settings", {
    headers: authHeaders(apiKey),
  });
}

export async function previewSettings(apiKey, body) {
  return fetchJson("/v1/frontend/settings:preview", {
    method: "POST",
    headers: authHeaders(apiKey),
    body: JSON.stringify(body),
  });
}

export async function applySettings(apiKey, body) {
  return fetchJson("/v1/frontend/settings:apply", {
    method: "POST",
    headers: authHeaders(apiKey),
    body: JSON.stringify(body),
  });
}

export async function restoreSettings(apiKey) {
  return fetchJson("/v1/frontend/settings:restore", {
    method: "POST",
    headers: authHeaders(apiKey),
    body: JSON.stringify({}),
  });
}

export async function loadDebugTimeline(apiKey, body) {
  return fetchJson("/v1/frontend/debug:timeline", {
    method: "POST",
    headers: authHeaders(apiKey),
    body: JSON.stringify(body),
  });
}
