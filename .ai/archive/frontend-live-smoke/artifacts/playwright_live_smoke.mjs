import fs from "node:fs/promises";
import path from "node:path";

const playwrightModulePath = process.env.PLAYWRIGHT_MODULE_PATH;
const { chromium } = playwrightModulePath
  ? await import(playwrightModulePath)
  : await import("playwright");

const ARTIFACT_DIR = path.resolve(
  ".ai/changes/frontend-live-smoke/artifacts",
);

async function ensureText(page, text) {
  await page.getByText(text, { exact: false }).waitFor();
}

async function run() {
  await fs.mkdir(ARTIFACT_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1512, height: 1120 } });

  const summary = {
    frontend_url: "http://127.0.0.1:5173",
    api_url: "http://127.0.0.1:18000",
    known_owner: "demo-user",
    anonymous_owner: "anon-live-smoke-1",
    observations: {},
  };

  try {
    await page.goto("http://127.0.0.1:5173", { waitUntil: "networkidle" });
    await ensureText(page, "MIND Workbench");
    await ensureText(page, "mind.application.MindService");

    await page.getByRole("button", { name: "Submit Ingestion" }).click();
    await ensureText(page, "[self] preference:like=black coffee");

    await page.getByRole("button", { name: "Run Search" }).click();
    await ensureText(page, "Search returned 1 memory item(s).");

    await page.getByRole("button", { name: "Load Memories" }).click();
    await page.locator(".memory-list-item").first().click();

    const updateArea = page.getByLabel("Manual Update Content");
    await updateArea.fill("[self] preference:like=americano");
    await page.getByRole("button", { name: "Save Update" }).click();
    await ensureText(page, "Updated memory");
    await ensureText(page, "UPDATE");
    await page.screenshot({
      path: path.join(ARTIFACT_DIR, "known-owner-flow.png"),
      fullPage: true,
    });

    await page.getByRole("button", { name: "Delete Memory" }).click();
    await ensureText(page, "Load memories to inspect this owner.");

    summary.observations.known_owner = {
      created_memory: "[self] preference:like=black coffee",
      search_query: "What should I drink?",
      updated_memory: "preference:like=americano",
      delete_state: "Load memories to inspect this owner.",
    };

    await page.getByRole("button", { name: "Anonymous Session" }).click();
    await page.getByPlaceholder("anon-session-123").fill("anon-live-smoke-1");

    const messageContent = page.locator("textarea").first();
    await messageContent.fill("I love green tea");

    await page.getByRole("button", { name: "Submit Ingestion" }).click();
    await ensureText(page, "[self] preference:like=green tea");

    await page.getByRole("button", { name: "Run Search" }).click();
    await ensureText(page, "Search returned 1 memory item(s).");
    await page.screenshot({
      path: path.join(ARTIFACT_DIR, "anonymous-owner-flow.png"),
      fullPage: true,
    });

    summary.observations.anonymous_owner = {
      created_memory: "[self] preference:like=green tea",
      search_query: "What should I drink?",
    };

    await fs.writeFile(
      path.join(ARTIFACT_DIR, "live_smoke_summary.json"),
      JSON.stringify(summary, null, 2),
      "utf-8",
    );
  } finally {
    await browser.close();
  }
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
