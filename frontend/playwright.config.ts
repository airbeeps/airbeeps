import { defineConfig, devices } from "@playwright/test";
import path from "path";
import fs from "fs";

/**
 * Playwright configuration for E2E tests.
 *
 * The webServer configuration starts both backend and frontend servers
 * automatically before running tests.
 *
 * IMPORTANT: Tests run serially (not in parallel) to avoid state conflicts
 * with "first user becomes admin" semantics and shared database.
 */

// E2E test data directory (relative to frontend/)
const E2E_DATA_DIR = path.resolve(__dirname, ".e2e-data");

// Generate unique run ID for test isolation in CI
const RUN_ID = process.env.CI ? `run-${Date.now()}` : "local";
const RUN_DATA_DIR = path.join(E2E_DATA_DIR, RUN_ID);

export default defineConfig({
  // Test directory
  testDir: "./tests/e2e",

  // Test file patterns
  testMatch: "**/*.spec.ts",

  // DISABLED: Parallel execution causes state conflicts with shared DB
  // Tests assume "first user becomes admin" which fails with parallelism
  fullyParallel: false,

  // Fail the build on CI if you accidentally left test.only in the source code
  forbidOnly: !!process.env.CI,

  // Retry on CI only
  retries: process.env.CI ? 2 : 0,

  // Single worker to ensure test isolation and deterministic ordering
  workers: 1,

  // Reporter to use
  reporter: [["html", { open: "never" }], ["list"]],

  // Shared settings for all projects
  use: {
    // Base URL to use in actions like `await page.goto('/')`
    baseURL: "http://localhost:3000",

    // Collect trace when retrying the failed test
    trace: "on-first-retry",

    // Take screenshot on failure
    screenshot: "only-on-failure",

    // Avoid networkidle which can be flaky with streaming/polling
    // Use explicit waits instead
  },

  // Configure projects for major browsers
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    // Uncomment to test on more browsers
    // {
    //   name: 'firefox',
    //   use: { ...devices['Desktop Firefox'] },
    // },
    // {
    //   name: 'webkit',
    //   use: { ...devices['Desktop Safari'] },
    // },
  ],

  // Global setup to clean database before tests
  globalSetup: "./tests/e2e/global-setup.ts",

  // Web servers to start before running tests
  webServer: [
    // Backend server - uses CLI which runs migrations automatically
    {
      command: `cd ../backend && uv run airbeeps run --host 127.0.0.1 --port 8500 --with-migrations`,
      url: "http://localhost:8500/api/v1/configs/public",
      // IMPORTANT: Always start fresh server in CI to avoid stale state
      reuseExistingServer: !process.env.CI,
      timeout: 120 * 1000,
      env: {
        // Enable test mode for fake LLM/embedding responses
        AIRBEEPS_TEST_MODE: "1",
        // Use a dedicated data directory for E2E tests
        // In CI, use unique run directory for isolation
        AIRBEEPS_DATA_ROOT: process.env.CI ? RUN_DATA_DIR : E2E_DATA_DIR,
        // Use a temp database (unique per run in CI)
        AIRBEEPS_DATABASE_URL: `sqlite+aiosqlite:///${path.join(
          process.env.CI ? RUN_DATA_DIR : E2E_DATA_DIR,
          "e2e.db"
        )}`,
        // Use embedded Chroma
        AIRBEEPS_CHROMA_SERVER_HOST: "",
        AIRBEEPS_CHROMA_PERSIST_DIR: path.join(
          process.env.CI ? RUN_DATA_DIR : E2E_DATA_DIR,
          "chroma"
        ),
        // Disable mail
        AIRBEEPS_MAIL_ENABLED: "false",
        // Test secret key
        AIRBEEPS_SECRET_KEY: "e2e-test-secret-key-not-for-production",
      },
    },
    // Frontend server
    {
      command: "pnpm dev",
      url: "http://localhost:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 120 * 1000,
    },
  ],

  // Output folder for test artifacts
  outputDir: "test-results/",
});
