import { defineConfig, devices } from "@playwright/test";

// Playwright UI automation for TRACE.
//
// These tests run against an already-running stack (Docker Compose or local dev)
// exposed at PLAYWRIGHT_BASE_URL (defaults to the Compose frontend on 5186).
// They drive the real API through the frontend's /api proxy, so no demo
// fallback data is used. Set PLAYWRIGHT_BASE_URL=http://127.0.0.1:5173 (or your
// vite dev port) to run against `npm run dev` instead.
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:5186";

export default defineConfig({
  testDir: "./e2e",
  // Experiment runs use MockLLM but still execute real pytest clean runs and
  // replays, so individual specs need a generous ceiling.
  timeout: 240_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  outputDir: "test-results",
  use: {
    baseURL,
    headless: true,
    viewport: { width: 1440, height: 900 },
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    screenshot: "only-on-failure",
    trace: "retain-on-failure"
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] }
    }
  ]
});
