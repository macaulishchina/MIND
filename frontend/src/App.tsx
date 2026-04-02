import { startTransition, useEffect, useState } from "react";
import {
  createChatCompletion,
  deleteMemory,
  getCapabilities,
  getMemory,
  getMemoryHistory,
  ingestConversation,
  listChatModels,
  listMemories,
  updateMemory,
  type Capabilities,
  type ChatMessage,
  type ChatModelProfile,
  type HistoryRecord,
  type MemoryRecord,
  type OwnerFormState,
  type OwnerMode,
} from "./lib/api";

type TranscriptMessage = ChatMessage & {
  id: string;
};

type BusyState = {
  bootstrap: boolean;
  chat: boolean;
  ingest: boolean;
  list: boolean;
  detail: boolean;
  update: boolean;
  remove: boolean;
};

type PersistedWorkbenchState = {
  ownerMode: OwnerMode;
  ownerValue: string;
  selectedModelId: string;
  conversationId: string;
  composerValue: string;
  submittedCount: number;
  transcript: TranscriptMessage[];
};

const STORAGE_KEY = "mind.chat-workbench.v2";

function emptyBusyState(): BusyState {
  return {
    bootstrap: true,
    chat: false,
    ingest: false,
    list: false,
    detail: false,
    update: false,
    remove: false,
  };
}

function nextId(prefix: string): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.round(Math.random() * 1_000_000)}`;
}

function newConversationId(): string {
  return nextId("conv");
}

function emptyTranscriptMessage(role: string, content: string): TranscriptMessage {
  return {
    id: nextId("msg"),
    role,
    content,
  };
}

function loadPersistedState(): PersistedWorkbenchState {
  const fallback: PersistedWorkbenchState = {
    ownerMode: "known",
    ownerValue: "demo-user",
    selectedModelId: "",
    conversationId: newConversationId(),
    composerValue: "",
    submittedCount: 0,
    transcript: [],
  };

  if (typeof window === "undefined") {
    return fallback;
  }

  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return fallback;
  }

  try {
    const parsed = JSON.parse(raw) as Partial<PersistedWorkbenchState>;
    return {
      ownerMode:
        parsed.ownerMode === "anonymous" || parsed.ownerMode === "known"
          ? parsed.ownerMode
          : fallback.ownerMode,
      ownerValue:
        typeof parsed.ownerValue === "string" && parsed.ownerValue.trim()
          ? parsed.ownerValue
          : fallback.ownerValue,
      selectedModelId:
        typeof parsed.selectedModelId === "string" ? parsed.selectedModelId : "",
      conversationId:
        typeof parsed.conversationId === "string" && parsed.conversationId
          ? parsed.conversationId
          : fallback.conversationId,
      composerValue:
        typeof parsed.composerValue === "string" ? parsed.composerValue : "",
      submittedCount:
        typeof parsed.submittedCount === "number" && parsed.submittedCount >= 0
          ? parsed.submittedCount
          : 0,
      transcript: Array.isArray(parsed.transcript)
        ? parsed.transcript
            .filter(
              (message): message is TranscriptMessage =>
                Boolean(
                  message &&
                    typeof message === "object" &&
                    typeof (message as TranscriptMessage).id === "string" &&
                    typeof (message as TranscriptMessage).role === "string" &&
                    typeof (message as TranscriptMessage).content === "string",
                ),
            )
            .map((message) => ({
              id: message.id,
              role: message.role,
              content: message.content,
            }))
        : [],
    };
  } catch {
    return fallback;
  }
}

function toApiMessages(messages: TranscriptMessage[]): ChatMessage[] {
  return messages
    .map((message) => ({
      role: message.role.trim(),
      content: message.content.trim(),
    }))
    .filter((message) => message.role && message.content);
}

function ownerLabel(mode: OwnerMode): string {
  return mode === "known" ? "Known User" : "Anonymous Session";
}

function ownerPlaceholder(mode: OwnerMode): string {
  return mode === "known" ? "customer-123" : "session-abc";
}

function messageRoleLabel(role: string): string {
  if (role === "assistant") {
    return "Assistant";
  }
  if (role === "system") {
    return "System";
  }
  return "You";
}

function messagePreview(memory: MemoryRecord): string {
  return memory.canonical_text ?? memory.content;
}

function isMessageSynced(index: number, submittedCount: number): boolean {
  return index < submittedCount;
}

function MessageBubble({
  message,
  index,
  submittedCount,
}: {
  message: TranscriptMessage;
  index: number;
  submittedCount: number;
}) {
  const synced = isMessageSynced(index, submittedCount);
  const bubbleClass =
    message.role === "assistant" ? "transcript-bubble assistant" : "transcript-bubble user";
  return (
    <article className={bubbleClass}>
      <div className="bubble-meta">
        <span>{messageRoleLabel(message.role)}</span>
        <strong>{synced ? "Memory synced" : "Pending memory submit"}</strong>
      </div>
      <p>{message.content}</p>
    </article>
  );
}

function MemoryList({
  items,
  selectedId,
  onSelect,
}: {
  items: MemoryRecord[];
  selectedId: string | null;
  onSelect: (memoryId: string) => void;
}) {
  if (items.length === 0) {
    return <div className="empty-block">No memories loaded for this owner yet.</div>;
  }

  return (
    <div className="memory-list">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          className={`memory-row ${selectedId === item.id ? "is-active" : ""}`}
          onClick={() => onSelect(item.id)}
        >
          <span>{item.subject_ref ?? "self"}</span>
          <strong>{messagePreview(item)}</strong>
        </button>
      ))}
    </div>
  );
}

function HistoryTimeline({ items }: { items: HistoryRecord[] }) {
  if (items.length === 0) {
    return <div className="empty-inline">No history for this memory yet.</div>;
  }

  return (
    <div className="timeline">
      {items.map((item) => (
        <article key={item.id} className="timeline-item">
          <div className="timeline-meta">
            <span>{item.operation}</span>
            <strong>{new Date(item.timestamp).toLocaleString()}</strong>
          </div>
          <p>{item.new_content ?? item.old_content ?? "No content recorded."}</p>
        </article>
      ))}
    </div>
  );
}

function RecentMemoryList({ items }: { items: MemoryRecord[] }) {
  if (items.length === 0) {
    return <div className="empty-inline">No new memory items from the last submit.</div>;
  }

  return (
    <div className="recent-memories">
      {items.map((item) => (
        <article key={item.id} className="recent-memory-card">
          <span>{item.fact_family ?? "memory"}</span>
          <strong>{messagePreview(item)}</strong>
        </article>
      ))}
    </div>
  );
}

export default function App() {
  const [persisted] = useState(loadPersistedState);

  const [ownerMode, setOwnerMode] = useState<OwnerMode>(persisted.ownerMode);
  const [ownerValue, setOwnerValue] = useState(persisted.ownerValue);
  const [selectedModelId, setSelectedModelId] = useState(persisted.selectedModelId);
  const [conversationId, setConversationId] = useState(persisted.conversationId);
  const [composerValue, setComposerValue] = useState(persisted.composerValue);
  const [transcript, setTranscript] = useState<TranscriptMessage[]>(persisted.transcript);
  const [submittedCount, setSubmittedCount] = useState(
    Math.min(persisted.submittedCount, persisted.transcript.length),
  );
  const [chatModels, setChatModels] = useState<ChatModelProfile[]>([]);
  const [memoryItems, setMemoryItems] = useState<MemoryRecord[]>([]);
  const [recentMemoryItems, setRecentMemoryItems] = useState<MemoryRecord[]>([]);
  const [selectedMemory, setSelectedMemory] = useState<MemoryRecord | null>(null);
  const [updateDraft, setUpdateDraft] = useState("");
  const [historyItems, setHistoryItems] = useState<HistoryRecord[]>([]);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [busy, setBusy] = useState<BusyState>(emptyBusyState());
  const [notice, setNotice] = useState("Loading chat workbench...");
  const [error, setError] = useState("");

  const owner: OwnerFormState = { mode: ownerMode, value: ownerValue };
  const pendingTurns = Math.max(0, transcript.length - submittedCount);
  const interactionLocked = busy.chat || busy.ingest;

  useEffect(() => {
    let active = true;
    Promise.all([getCapabilities(), listChatModels()])
      .then(([capabilityData, chatModelData]) => {
        if (!active) {
          return;
        }
        startTransition(() => {
          setCapabilities(capabilityData);
          setChatModels(chatModelData.items);
          setSelectedModelId((current) => {
            if (current && chatModelData.items.some((item) => item.id === current)) {
              return current;
            }
            return (
              chatModelData.items.find((item) => item.is_default)?.id ??
              chatModelData.items[0]?.id ??
              ""
            );
          });
          setNotice("Chat workbench is ready.");
        });
      })
      .catch((err: Error) => {
        if (!active) {
          return;
        }
        setError(`Workbench bootstrap failed: ${err.message}`);
      })
      .finally(() => {
        if (!active) {
          return;
        }
        setBusy((current) => ({ ...current, bootstrap: false }));
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        ownerMode,
        ownerValue,
        selectedModelId,
        conversationId,
        composerValue,
        submittedCount,
        transcript,
      } satisfies PersistedWorkbenchState),
    );
  }, [
    ownerMode,
    ownerValue,
    selectedModelId,
    conversationId,
    composerValue,
    submittedCount,
    transcript,
  ]);

  useEffect(() => {
    startTransition(() => {
      setMemoryItems([]);
      setSelectedMemory(null);
      setUpdateDraft("");
      setHistoryItems([]);
      setRecentMemoryItems([]);
    });
  }, [ownerMode, ownerValue]);

  function setBusyFlag(flag: keyof BusyState, value: boolean) {
    setBusy((current) => ({ ...current, [flag]: value }));
  }

  function clearFeedback() {
    setError("");
    setNotice("");
  }

  async function refreshMemoryList(preserveSelected = true) {
    if (!owner.value.trim()) {
      setError("Owner value is required.");
      return;
    }

    setBusyFlag("list", true);
    try {
      const response = await listMemories(owner);
      startTransition(() => {
        setMemoryItems(response.items);
        if (!preserveSelected) {
          setSelectedMemory(null);
          setUpdateDraft("");
          setHistoryItems([]);
          return;
        }
        if (selectedMemory) {
          const updated = response.items.find((item) => item.id === selectedMemory.id);
          if (updated) {
            setSelectedMemory(updated);
          } else {
            setSelectedMemory(null);
            setUpdateDraft("");
            setHistoryItems([]);
          }
        }
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyFlag("list", false);
    }
  }

  async function selectMemory(memoryId: string) {
    setBusyFlag("detail", true);
    clearFeedback();
    try {
      const [memory, history] = await Promise.all([
        getMemory(memoryId),
        getMemoryHistory(memoryId),
      ]);
      startTransition(() => {
        setSelectedMemory(memory);
        setUpdateDraft(memory.canonical_text ?? memory.content);
        setHistoryItems(history.items);
        setNotice(`Loaded memory ${memoryId}.`);
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyFlag("detail", false);
    }
  }

  async function handleSendMessage() {
    clearFeedback();

    if (!owner.value.trim()) {
      setError("Owner value is required.");
      return;
    }
    if (!selectedModelId) {
      setError("Select a chat model first.");
      return;
    }
    if (!composerValue.trim()) {
      setError("Type a message before sending.");
      return;
    }

    const nextTranscript = [
      ...transcript,
      emptyTranscriptMessage("user", composerValue.trim()),
    ];

    setTranscript(nextTranscript);
    setComposerValue("");
    setBusyFlag("chat", true);

    try {
      const response = await createChatCompletion(
        owner,
        selectedModelId,
        toApiMessages(nextTranscript),
      );
      const assistantMessage = emptyTranscriptMessage(
        response.message.role,
        response.message.content,
      );
      startTransition(() => {
        setTranscript([...nextTranscript, assistantMessage]);
        setNotice(`Responded with ${response.provider}/${response.model}.`);
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyFlag("chat", false);
    }
  }

  async function handleSubmitMemory() {
    clearFeedback();

    if (!owner.value.trim()) {
      setError("Owner value is required.");
      return;
    }

    const pendingMessages = toApiMessages(transcript.slice(submittedCount));
    if (pendingMessages.length === 0) {
      setNotice("No new conversation turns to submit.");
      return;
    }

    const currentTranscriptLength = transcript.length;
    setBusyFlag("ingest", true);
    try {
      const response = await ingestConversation(owner, pendingMessages, conversationId, {
        source: "frontend-workbench",
        chat_model_profile_id: selectedModelId,
      });
      startTransition(() => {
        setSubmittedCount(currentTranscriptLength);
        setRecentMemoryItems(response.items);
        setNotice(
          `Submitted ${pendingMessages.length} new turn(s) and created ${response.count} memory item(s).`,
        );
      });
      await refreshMemoryList();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyFlag("ingest", false);
    }
  }

  async function handleUpdate() {
    if (!selectedMemory) {
      setError("Select a memory before updating.");
      return;
    }
    if (!updateDraft.trim()) {
      setError("Update content is required.");
      return;
    }

    clearFeedback();
    setBusyFlag("update", true);
    try {
      const updated = await updateMemory(selectedMemory.id, updateDraft.trim());
      const history = await getMemoryHistory(selectedMemory.id);
      startTransition(() => {
        setSelectedMemory(updated);
        setUpdateDraft(updated.canonical_text ?? updated.content);
        setHistoryItems(history.items);
        setNotice(`Updated memory ${selectedMemory.id}.`);
      });
      await refreshMemoryList();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyFlag("update", false);
    }
  }

  async function handleDelete() {
    if (!selectedMemory) {
      setError("Select a memory before deleting.");
      return;
    }

    clearFeedback();
    setBusyFlag("remove", true);
    try {
      await deleteMemory(selectedMemory.id);
      startTransition(() => {
        setSelectedMemory(null);
        setUpdateDraft("");
        setHistoryItems([]);
        setNotice(`Deleted memory ${selectedMemory.id}.`);
      });
      await refreshMemoryList(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyFlag("remove", false);
    }
  }

  function handleNewChat() {
    clearFeedback();
    startTransition(() => {
      setTranscript([]);
      setComposerValue("");
      setSubmittedCount(0);
      setConversationId(newConversationId());
      setRecentMemoryItems([]);
      setNotice("Started a new conversation.");
    });
  }

  return (
    <div className="chat-shell">
      <div className="chat-shell__glow" />
      <div className="chat-workbench">
        <header className="topbar">
          <div>
            <p className="eyebrow">Internal Workbench</p>
            <h1>MIND Chat Console</h1>
            <p className="topbar-copy">
              Chat like a normal LLM app, then submit only the new turns into MIND
              memory.
            </p>
          </div>
          <div className="topbar-meta">
            <span>{capabilities?.version ?? "loading"}</span>
            <strong>{capabilities?.application_entrypoint ?? "Bootstrapping..."}</strong>
          </div>
        </header>

        {notice ? <div className="banner banner-note">{notice}</div> : null}
        {error ? <div className="banner banner-error">{error}</div> : null}

        <div className="workspace-grid">
          <main className="chat-column">
            <section className="chat-panel">
              <div className="chat-panel__header">
                <div>
                  <span className="section-label">Main Workspace</span>
                  <h2>Conversation</h2>
                </div>
                <div className="sync-pill">
                  <span>{pendingTurns} pending</span>
                  <strong>{submittedCount} synced</strong>
                </div>
              </div>

              <div className="toolbar-card">
                <div className="toolbar-grid">
                  <div className="segmented-field">
                    <span className="field-label">Owner Type</span>
                    <div className="segmented-control">
                      <button
                        type="button"
                        className={ownerMode === "known" ? "is-active" : ""}
                        onClick={() => setOwnerMode("known")}
                        disabled={interactionLocked}
                      >
                        Known
                      </button>
                      <button
                        type="button"
                        className={ownerMode === "anonymous" ? "is-active" : ""}
                        onClick={() => setOwnerMode("anonymous")}
                        disabled={interactionLocked}
                      >
                        Anonymous
                      </button>
                    </div>
                  </div>

                  <label className="field">
                    <span className="field-label">{ownerLabel(ownerMode)}</span>
                    <input
                      aria-label="Owner Value"
                      value={ownerValue}
                      onChange={(event) => setOwnerValue(event.target.value)}
                      placeholder={ownerPlaceholder(ownerMode)}
                      disabled={interactionLocked}
                    />
                  </label>

                  <label className="field">
                    <span className="field-label">Chat Model</span>
                    <select
                      aria-label="Chat Model"
                      value={selectedModelId}
                      onChange={(event) => setSelectedModelId(event.target.value)}
                      disabled={busy.bootstrap || interactionLocked}
                    >
                      {chatModels.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.label} · {item.provider}/{item.model}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <p className="toolbar-note">
                  Only curated chat profiles are switchable here. STL extraction and
                  decision models stay in backend TOML.
                </p>
              </div>

              <div className="transcript-panel" aria-live="polite">
                {transcript.length === 0 ? (
                  <div className="empty-chat">
                    <span>Start with a normal prompt.</span>
                    <strong>
                      After a few turns, click <em>Submit Memory</em> to store only the
                      new dialogue.
                    </strong>
                  </div>
                ) : (
                  transcript.map((message, index) => (
                    <MessageBubble
                      key={message.id}
                      message={message}
                      index={index}
                      submittedCount={submittedCount}
                    />
                  ))
                )}
              </div>

              <div className="composer-card">
                <label className="composer-field">
                  <span className="field-label">Message</span>
                  <textarea
                    aria-label="Chat Message"
                    value={composerValue}
                    onChange={(event) => setComposerValue(event.target.value)}
                    rows={4}
                    placeholder="Ask something natural, like a normal chat app."
                    disabled={interactionLocked}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        if (!interactionLocked) {
                          void handleSendMessage();
                        }
                      }
                    }}
                  />
                </label>

                <div className="composer-actions">
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={handleNewChat}
                    disabled={interactionLocked}
                  >
                    New Chat
                  </button>
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={() => void handleSubmitMemory()}
                    disabled={interactionLocked || transcript.length === 0}
                  >
                    {busy.ingest ? "Submitting..." : "Submit Memory"}
                  </button>
                  <button
                    type="button"
                    className="primary-button"
                    onClick={() => void handleSendMessage()}
                    disabled={busy.bootstrap || interactionLocked}
                  >
                    {busy.chat ? "Thinking..." : "Send"}
                  </button>
                </div>
              </div>

              <section className="subpanel">
                <div className="subpanel__header">
                  <div>
                    <span className="section-label">Last Memory Submit</span>
                    <h3>Created Memory Items</h3>
                  </div>
                  <span>{recentMemoryItems.length} item(s)</span>
                </div>
                <RecentMemoryList items={recentMemoryItems} />
              </section>
            </section>
          </main>

          <aside className="explorer-column">
            <section className="explorer-panel">
              <div className="explorer-panel__header">
                <div>
                  <span className="section-label">Explorer</span>
                  <h2>Memory Explorer</h2>
                </div>
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => void refreshMemoryList()}
                  disabled={busy.list || interactionLocked}
                >
                  {busy.list ? "Refreshing..." : "Refresh Memories"}
                </button>
              </div>

              <MemoryList
                items={memoryItems}
                selectedId={selectedMemory?.id ?? null}
                onSelect={(memoryId) => void selectMemory(memoryId)}
              />

              <div className="detail-card">
                {selectedMemory ? (
                  <>
                    <div className="detail-grid">
                      <div>
                        <span className="field-label">Memory ID</span>
                        <strong>{selectedMemory.id}</strong>
                      </div>
                      <div>
                        <span className="field-label">Subject</span>
                        <strong>{selectedMemory.subject_ref ?? "self"}</strong>
                      </div>
                      <div>
                        <span className="field-label">Family</span>
                        <strong>{selectedMemory.fact_family ?? "memory"}</strong>
                      </div>
                      <div>
                        <span className="field-label">Status</span>
                        <strong>{selectedMemory.status}</strong>
                      </div>
                    </div>

                    <label className="field">
                      <span className="field-label">Manual Update Content</span>
                      <textarea
                        aria-label="Manual Update Content"
                        rows={4}
                        value={updateDraft}
                        onChange={(event) => setUpdateDraft(event.target.value)}
                      />
                    </label>

                    <div className="detail-actions">
                      <button
                        type="button"
                        className="ghost-button"
                        onClick={() => void handleDelete()}
                        disabled={busy.remove}
                      >
                        {busy.remove ? "Deleting..." : "Delete Memory"}
                      </button>
                      <button
                        type="button"
                        className="primary-button"
                        onClick={() => void handleUpdate()}
                        disabled={busy.update}
                      >
                        {busy.update ? "Saving..." : "Save Update"}
                      </button>
                    </div>

                    <div className="history-block">
                      <div className="subpanel__header compact">
                        <div>
                          <span className="section-label">Timeline</span>
                          <h3>History</h3>
                        </div>
                      </div>
                      <HistoryTimeline items={historyItems} />
                    </div>
                  </>
                ) : (
                  <div className="empty-block">Refresh memories and choose one to inspect.</div>
                )}
              </div>
            </section>
          </aside>
        </div>
      </div>
    </div>
  );
}
