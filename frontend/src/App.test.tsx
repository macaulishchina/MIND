import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function emptyResponse(status = 204) {
  return Promise.resolve(new Response(null, { status }));
}

describe("App", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.stubGlobal("fetch", vi.fn());
  });

  it("runs the chat flow and submits only new turns to memory", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockImplementationOnce(() =>
        jsonResponse({
          version: "0.1.0",
          application_entrypoint: "mind.application.MindService",
          adapters: { rest: true, mcp: false, cli: false },
          operations: ["list_chat_models", "chat_completion", "ingest_conversation"],
          owner_selector_modes: ["external_user_id", "anonymous_session_id"],
        }),
      )
      .mockImplementationOnce(() =>
        jsonResponse({
          count: 2,
          items: [
            {
              id: "fast",
              label: "Fast",
              provider: "fake",
              model: "fake-fast",
              temperature: 0,
              timeout: 15,
              is_default: true,
            },
            {
              id: "careful",
              label: "Careful",
              provider: "fake",
              model: "fake-careful",
              temperature: 0.2,
              timeout: 30,
              is_default: false,
            },
          ],
        }),
      )
      .mockImplementationOnce(() =>
        jsonResponse({
          message: { role: "assistant", content: "echo: coffee is great" },
          model_profile_id: "fast",
          provider: "fake",
          model: "fake-fast",
        }),
      )
      .mockImplementationOnce(() =>
        jsonResponse({
          count: 1,
          items: [
            {
              id: "mem-1",
              user_id: "demo-user",
              content: "like(self, black coffee)",
              canonical_text: "like(self, black coffee)",
              hash: "hash-1",
              metadata: {},
              status: "active",
            },
          ],
        }),
      )
      .mockImplementationOnce(() => jsonResponse({ count: 1, items: [] }))
      .mockImplementationOnce(() =>
        jsonResponse({
          message: { role: "assistant", content: "echo: americano works too" },
          model_profile_id: "fast",
          provider: "fake",
          model: "fake-fast",
        }),
      )
      .mockImplementationOnce(() =>
        jsonResponse({
          count: 1,
          items: [
            {
              id: "mem-2",
              user_id: "demo-user",
              content: "drink(self, americano)",
              canonical_text: "drink(self, americano)",
              hash: "hash-2",
              metadata: {},
              status: "active",
            },
          ],
        }),
      )
      .mockImplementationOnce(() => jsonResponse({ count: 2, items: [] }));

    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("mind.application.MindService");

    const composer = screen.getByLabelText("Chat Message");
    await user.type(composer, "I love black coffee");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText("echo: coffee is great");

    await user.click(screen.getByRole("button", { name: "Submit Memory" }));

    await screen.findByText("like(self, black coffee)");

    await user.clear(composer);
    await user.type(composer, "Maybe I should switch to americano");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText("echo: americano works too");
    await user.click(screen.getByRole("button", { name: "Submit Memory" }));

    const firstIngestCall = fetchMock.mock.calls.find(
      ([url]) => url === "http://127.0.0.1:8000/api/v1/ingestions",
    );
    const secondIngestCall = fetchMock.mock.calls.filter(
      ([url]) => url === "http://127.0.0.1:8000/api/v1/ingestions",
    )[1];

    expect(firstIngestCall).toBeDefined();
    expect(secondIngestCall).toBeDefined();

    const firstPayload = JSON.parse(String(firstIngestCall?.[1]?.body));
    const secondPayload = JSON.parse(String(secondIngestCall?.[1]?.body));

    expect(firstPayload.messages).toHaveLength(2);
    expect(firstPayload.messages[0].content).toBe("I love black coffee");
    expect(secondPayload.messages).toHaveLength(2);
    expect(secondPayload.messages[0].content).toBe(
      "Maybe I should switch to americano",
    );
  });

  it("loads memories, updates one, and deletes it from the explorer", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockImplementationOnce(() =>
        jsonResponse({
          version: "0.1.0",
          application_entrypoint: "mind.application.MindService",
          adapters: { rest: true, mcp: false, cli: false },
          operations: ["list_chat_models", "chat_completion", "ingest_conversation"],
          owner_selector_modes: ["external_user_id", "anonymous_session_id"],
        }),
      )
      .mockImplementationOnce(() =>
        jsonResponse({
          count: 1,
          items: [
            {
              id: "fast",
              label: "Fast",
              provider: "fake",
              model: "fake-fast",
              temperature: 0,
              timeout: 15,
              is_default: true,
            },
          ],
        }),
      )
      .mockImplementationOnce(() =>
        jsonResponse({
          count: 1,
          items: [
            {
              id: "mem-2",
              user_id: "demo-user",
              content: "like(self, black coffee)",
              canonical_text: "like(self, black coffee)",
              hash: "hash-2",
              metadata: {},
              status: "active",
              subject_ref: "self",
              fact_family: "preference",
            },
          ],
        }),
      )
      .mockImplementationOnce(() =>
        jsonResponse({
          id: "mem-2",
          user_id: "demo-user",
          content: "like(self, black coffee)",
          canonical_text: "like(self, black coffee)",
          hash: "hash-2",
          metadata: {},
          status: "active",
          subject_ref: "self",
          fact_family: "preference",
        }),
      )
      .mockImplementationOnce(() =>
        jsonResponse({
          count: 1,
          items: [
            {
              id: "hist-1",
              memory_id: "mem-2",
              user_id: "demo-user",
              operation: "ADD",
              old_content: null,
              new_content: "like(self, black coffee)",
              timestamp: "2026-04-02T12:00:00Z",
              metadata: {},
            },
          ],
        }),
      )
      .mockImplementationOnce(() =>
        jsonResponse({
          id: "mem-2",
          user_id: "demo-user",
          content: "like(self, americano)",
          canonical_text: "like(self, americano)",
          hash: "hash-3",
          metadata: {},
          status: "active",
          subject_ref: "self",
          fact_family: "preference",
        }),
      )
      .mockImplementationOnce(() =>
        jsonResponse({
          count: 2,
          items: [
            {
              id: "hist-1",
              memory_id: "mem-2",
              user_id: "demo-user",
              operation: "ADD",
              old_content: null,
              new_content: "like(self, black coffee)",
              timestamp: "2026-04-02T12:00:00Z",
              metadata: {},
            },
            {
              id: "hist-2",
              memory_id: "mem-2",
              user_id: "demo-user",
              operation: "UPDATE",
              old_content: "like(self, black coffee)",
              new_content: "like(self, americano)",
              timestamp: "2026-04-02T12:01:00Z",
              metadata: {},
            },
          ],
        }),
      )
      .mockImplementationOnce(() =>
        jsonResponse({
          count: 1,
          items: [
            {
              id: "mem-2",
              user_id: "demo-user",
              content: "like(self, americano)",
              canonical_text: "like(self, americano)",
              hash: "hash-3",
              metadata: {},
              status: "active",
              subject_ref: "self",
              fact_family: "preference",
            },
          ],
        }),
      )
      .mockImplementationOnce(() => emptyResponse(204))
      .mockImplementationOnce(() => jsonResponse({ count: 0, items: [] }));

    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("mind.application.MindService");
    await user.click(screen.getByRole("button", { name: "Refresh Memories" }));
    await user.click(
      await screen.findByRole("button", { name: /like\(self, black coffee\)/i }),
    );

    const updateInput = await screen.findByLabelText("Manual Update Content");
    await user.clear(updateInput);
    await user.type(updateInput, "like(self, americano)");
    await user.click(screen.getByRole("button", { name: "Save Update" }));

    await waitFor(() => {
      expect(screen.getByDisplayValue("like(self, americano)")).toBeInTheDocument();
    });
    await screen.findByText("UPDATE");

    await user.click(screen.getByRole("button", { name: "Delete Memory" }));

    await waitFor(() => {
      expect(
        screen.getByText("Refresh memories and choose one to inspect."),
      ).toBeInTheDocument();
    });
  });

  it("switches to anonymous owner mode for chat and memory submit", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockImplementationOnce(() =>
        jsonResponse({
          version: "0.1.0",
          application_entrypoint: "mind.application.MindService",
          adapters: { rest: true, mcp: false, cli: false },
          operations: ["list_chat_models", "chat_completion", "ingest_conversation"],
          owner_selector_modes: ["external_user_id", "anonymous_session_id"],
        }),
      )
      .mockImplementationOnce(() =>
        jsonResponse({
          count: 1,
          items: [
            {
              id: "fast",
              label: "Fast",
              provider: "fake",
              model: "fake-fast",
              temperature: 0,
              timeout: 15,
              is_default: true,
            },
          ],
        }),
      )
      .mockImplementationOnce(() =>
        jsonResponse({
          message: { role: "assistant", content: "echo: green tea works" },
          model_profile_id: "fast",
          provider: "fake",
          model: "fake-fast",
        }),
      )
      .mockImplementationOnce(() =>
        jsonResponse({
          count: 1,
          items: [
            {
              id: "mem-9",
              user_id: "anon-frontend-1",
              content: "like(self, green tea)",
              canonical_text: "like(self, green tea)",
              hash: "hash-9",
              metadata: {},
              status: "active",
            },
          ],
        }),
      )
      .mockImplementationOnce(() => jsonResponse({ count: 1, items: [] }));

    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("mind.application.MindService");
    await user.click(screen.getByRole("button", { name: "Anonymous" }));
    await user.clear(screen.getByLabelText("Owner Value"));
    await user.type(screen.getByLabelText("Owner Value"), "anon-frontend-1");
    await user.type(screen.getByLabelText("Chat Message"), "I love green tea");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText("echo: green tea works");
    await user.click(screen.getByRole("button", { name: "Submit Memory" }));

    const chatPayload = JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body));
    const ingestPayload = JSON.parse(String(fetchMock.mock.calls[3]?.[1]?.body));

    expect(chatPayload.owner).toEqual({ anonymous_session_id: "anon-frontend-1" });
    expect(ingestPayload.owner).toEqual({ anonymous_session_id: "anon-frontend-1" });
  });
});
