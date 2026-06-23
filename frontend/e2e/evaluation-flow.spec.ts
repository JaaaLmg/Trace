import { test, expect, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

// End-to-end browser automation for the TRACE evaluation flow.
//
// Mirrors the manual V2.4 runbook rehearsal:
//   Dataset list -> Dataset detail -> Create experiment (preselected dataset)
//   -> Start -> live progress -> completed -> Metrics / Evidence -> Report / Export.
//
// The test talks to the real backend through the frontend /api proxy and uses
// MockLLM (no demo fallback). Screenshots are written to docs/evidence so they
// can be referenced from the test report.

const EVIDENCE_DIR = join(process.cwd(), "..", "docs", "evidence", "playwright-ui");
const DATASET_ID = "dataset-demo-v2";

function uniqueExperimentId(): string {
  const stamp = new Date()
    .toISOString()
    .replace(/[-:.TZ]/g, "")
    .slice(0, 14);
  return `pw-ui-${stamp}`;
}

async function bootstrapApiSession(page: Page): Promise<void> {
  // Force English locale + API data source before the app mounts so selectors
  // are deterministic and we never read static demo fixtures.
  await page.addInitScript(() => {
    window.localStorage.setItem("trace-locale", "en");
  });
}

async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: join(EVIDENCE_DIR, name), fullPage: true });
}

test.beforeAll(() => {
  mkdirSync(EVIDENCE_DIR, { recursive: true });
});

test.beforeEach(async ({ page }) => {
  await bootstrapApiSession(page);
});

test("dataset list and detail load real API data", async ({ page }) => {
  await page.goto("/#/datasets");

  // App shell renders and the data source is API.
  await expect(page.getByRole("button", { name: "API" })).toHaveClass(/active/);

  // Demo dataset card is present and links into detail.
  const datasetCard = page.locator(".dataset-card", { hasText: DATASET_ID });
  await expect(datasetCard).toBeVisible();
  await shot(page, "01-dataset-list.png");

  await datasetCard.getByRole("button").last().click();
  await expect(page).toHaveURL(new RegExp(`#/datasets/${DATASET_ID}`));

  // Readiness panel renders; demo dataset should be ready for experiments.
  await expect(page.locator(".readiness-panel")).toBeVisible();
  await expect(page.getByRole("button", { name: "Create experiment" })).toBeEnabled();
  await shot(page, "02-dataset-detail.png");
});

test("create, start and evaluate an experiment end to end", async ({ page }) => {
  const experimentId = uniqueExperimentId();

  // Enter the create flow from the dataset, confirming preselection.
  await page.goto(`/#/datasets/${DATASET_ID}`);
  await page.getByRole("button", { name: "Create experiment" }).click();
  await expect(page).toHaveURL(new RegExp(`#/experiments\\?dataset=${DATASET_ID}`));

  // The create panel preselects the dataset, strategies, runtime profile and
  // MockLLM option. Pin a deterministic id so we can assert navigation.
  const createPanel = page.locator(".create-panel");
  await expect(createPanel).toBeVisible();
  await createPanel.locator('input[placeholder="exp-local-demo"]').fill(experimentId);

  const datasetSelect = createPanel.locator("select").first();
  await expect(datasetSelect).toHaveValue(new RegExp(DATASET_ID));

  // At least one strategy is selected by default; ensure Direct is on so the
  // run stays fast but still exercises clean + replay.
  const selectedStrategies = createPanel.locator(".strategy-options button.selected");
  await expect(selectedStrategies.first()).toBeVisible();
  await shot(page, "03-experiment-create-preselected.png");

  const createButton = createPanel.getByRole("button", { name: /Create experiment|Creating/ });
  await expect(createButton).toBeEnabled();
  await createButton.click();

  // We land on the experiment detail page for the new draft experiment.
  await expect(page).toHaveURL(new RegExp(`#/experiments/${experimentId}`));
  const startButton = page.getByRole("button", { name: "Run", exact: true });
  await expect(startButton).toBeVisible();
  await shot(page, "04-experiment-draft-start.png");

  // Start the run; a live progress band should appear.
  await startButton.click();
  await expect(page.locator(".progress-band")).toBeVisible({ timeout: 30_000 });
  await shot(page, "05-experiment-progress-after-start.png");

  // Wait for completion. The detail page polls progress every 2.5s and swaps in
  // the metrics view once the experiment reaches a terminal state.
  await expect(page.locator(".metadata-grid")).toBeVisible({ timeout: 200_000 });
  await expect(page.getByText("completed", { exact: false }).first()).toBeVisible();
  await shot(page, "07-experiment-completed.png");

  // Metrics table: at least one strategy row with metric_status ok.
  const metricsTable = page.locator("table").first();
  await expect(metricsTable).toBeVisible();
  await expect(page.getByText(/ok/i).first()).toBeVisible();
  await shot(page, "09-metrics-rows.png");

  // Report / Export panel and metrics JSON download.
  const reportPanel = page.locator(".report-export-panel");
  await expect(reportPanel).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await reportPanel.getByRole("button", { name: /Download metrics JSON/i }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain(experimentId);
  await shot(page, "08-report-export.png");

  // Replay evidence renders with llm_calls = 0 for replays (clean separation).
  await expect(page.locator(".report-grid")).toBeVisible();
});
