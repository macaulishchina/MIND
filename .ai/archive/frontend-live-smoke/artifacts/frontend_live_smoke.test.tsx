import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import App from "../../../../frontend/src/App";

const ARTIFACT_DIR = path.dirname(fileURLToPath(import.meta.url));

it(
  "runs the frontend workbench against the live smoke REST backend",
  async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("mind.application.MindService", {}, { timeout: 10000 });

    await user.click(screen.getByRole("button", { name: "Submit Ingestion" }));
    await waitFor(() => {
      expect(
        screen.getAllByText("[self] preference:like=black coffee").length,
      ).toBeGreaterThan(0);
    });

    await user.click(screen.getByRole("button", { name: "Run Search" }));
    await screen.findByText("Search returned 1 memory item(s).");

    await user.click(screen.getByRole("button", { name: "Load Memories" }));
    await user.click(
      await screen.findByRole("button", {
        name: /\[self\] preference:like=black coffee/i,
      }),
    );

    const updateInput = await screen.findByLabelText("Manual Update Content");
    await user.clear(updateInput);
    await user.type(updateInput, "[self] preference:like=americano");
    await user.click(screen.getByRole("button", { name: "Save Update" }));

    await waitFor(() => {
      expect(
        screen.getAllByText("preference:like=americano").length,
      ).toBeGreaterThan(0);
    });
    await screen.findByText("UPDATE");

    await user.click(screen.getByRole("button", { name: "Delete Memory" }));
    await screen.findByText("Load memories to inspect this owner.");

    await user.click(screen.getByRole("button", { name: "Anonymous Session" }));
    const ownerInput = screen.getByPlaceholderText("anon-session-123");
    await user.clear(ownerInput);
    await user.type(ownerInput, "anon-live-smoke-1");

    const contentInput = screen.getAllByLabelText("Content")[0];
    await user.clear(contentInput);
    await user.type(contentInput, "I love green tea");

    await user.click(screen.getByRole("button", { name: "Submit Ingestion" }));
    await waitFor(() => {
      expect(
        screen.getAllByText("[self] preference:like=green tea").length,
      ).toBeGreaterThan(0);
    });

    await user.click(screen.getByRole("button", { name: "Run Search" }));
    await screen.findByText("Search returned 1 memory item(s).");

    await fs.writeFile(
      path.join(ARTIFACT_DIR, "live_smoke_summary.json"),
      JSON.stringify(
        {
          frontend_url: "http://127.0.0.1:5173",
          api_url: "http://127.0.0.1:18000",
          known_owner: {
            owner_id: "demo-user",
            created_memory: "[self] preference:like=black coffee",
            updated_memory: "preference:like=americano",
            delete_state: "Load memories to inspect this owner.",
          },
          anonymous_owner: {
            owner_id: "anon-live-smoke-1",
            created_memory: "[self] preference:like=green tea",
          },
        },
        null,
        2,
      ),
      "utf-8",
    );
  },
  30000,
);
