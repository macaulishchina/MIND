export type OwnerMode = "known" | "anonymous";

export interface OwnerFormState {
  mode: OwnerMode;
  value: string;
}

export interface ChatMessage {
  role: string;
  content: string;
}

export interface MemoryRecord {
  id: string;
  user_id: string;
  owner_id?: string | null;
  content: string;
  hash: string;
  metadata: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
  confidence?: number | null;
  status: string;
  source_context?: string | null;
  source_session_id?: string | null;
  version_of?: string | null;
  importance?: number | null;
  type?: string | null;
  subject_ref?: string | null;
  fact_family?: string | null;
  relation_type?: string | null;
  field_key?: string | null;
  field_value_json?: Record<string, unknown> | null;
  canonical_text?: string | null;
  raw_text?: string | null;
  score?: number | null;
}

export interface HistoryRecord {
  id: string;
  memory_id: string;
  user_id: string;
  operation: string;
  old_content?: string | null;
  new_content?: string | null;
  timestamp: string;
  metadata: Record<string, unknown>;
}

export interface Capabilities {
  version: string;
  application_entrypoint: string;
  adapters: Record<string, boolean>;
  operations: string[];
  owner_selector_modes: string[];
}

interface CollectionResponse<T> {
  items: T[];
  count: number;
}

export interface ChatModelProfile {
  id: string;
  label: string;
  provider: string;
  model: string;
  temperature: number;
  timeout: number;
  is_default: boolean;
}

interface ChatCompletionResult {
  message: ChatMessage;
  model_profile_id: string;
  provider: string;
  model: string;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

function ownerPayload(owner: OwnerFormState): Record<string, string> {
  const value = owner.value.trim();
  if (!value) {
    throw new Error("Owner value is required");
  }
  return owner.mode === "known"
    ? { external_user_id: value }
    : { anonymous_session_id: value };
}

function ownerQuery(owner: OwnerFormState): string {
  const params = new URLSearchParams(ownerPayload(owner));
  return params.toString();
}

function formatDetail(detail: unknown): string {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return JSON.stringify(item);
      })
      .join("; ");
  }
  if (detail && typeof detail === "object") {
    return JSON.stringify(detail);
  }
  return "Unknown error";
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(formatDetail(data?.detail ?? data));
  }
  return data as T;
}

export async function getCapabilities(): Promise<Capabilities> {
  return requestJson<Capabilities>("/api/v1/capabilities");
}

export async function listChatModels(): Promise<CollectionResponse<ChatModelProfile>> {
  return requestJson("/api/v1/chat/models");
}

export async function createChatCompletion(
  owner: OwnerFormState,
  modelProfileId: string,
  messages: ChatMessage[],
): Promise<ChatCompletionResult> {
  return requestJson("/api/v1/chat/completions", {
    method: "POST",
    body: JSON.stringify({
      owner: ownerPayload(owner),
      model_profile_id: modelProfileId,
      messages,
    }),
  });
}

export async function ingestConversation(
  owner: OwnerFormState,
  messages: ChatMessage[],
  sessionId?: string,
  metadata?: Record<string, unknown>,
): Promise<CollectionResponse<MemoryRecord>> {
  return requestJson("/api/v1/ingestions", {
    method: "POST",
    body: JSON.stringify({
      owner: ownerPayload(owner),
      messages,
      session_id: sessionId,
      metadata,
    }),
  });
}

export async function searchMemories(
  owner: OwnerFormState,
  query: string,
): Promise<CollectionResponse<MemoryRecord>> {
  return requestJson("/api/v1/memories/search", {
    method: "POST",
    body: JSON.stringify({
      owner: ownerPayload(owner),
      query,
    }),
  });
}

export async function listMemories(
  owner: OwnerFormState,
): Promise<CollectionResponse<MemoryRecord>> {
  return requestJson(`/api/v1/memories?${ownerQuery(owner)}`);
}

export async function getMemory(memoryId: string): Promise<MemoryRecord> {
  return requestJson(`/api/v1/memories/${memoryId}`);
}

export async function updateMemory(
  memoryId: string,
  content: string,
): Promise<MemoryRecord> {
  return requestJson(`/api/v1/memories/${memoryId}`, {
    method: "PATCH",
    body: JSON.stringify({ content }),
  });
}

export async function deleteMemory(memoryId: string): Promise<void> {
  await requestJson(`/api/v1/memories/${memoryId}`, {
    method: "DELETE",
  });
}

export async function getMemoryHistory(
  memoryId: string,
): Promise<CollectionResponse<HistoryRecord>> {
  return requestJson(`/api/v1/memories/${memoryId}/history`);
}
