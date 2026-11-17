import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end smoke tests (F13). They drive a production build of the dashboard in mock mode, so
 * they need no backend: every response comes from contract/fixtures through lib/api/mock.ts.
 *
 * Browser: Microsoft Edge on Windows (it ships with the OS, so nothing has to be downloaded),
 * Playwright's own Chromium elsewhere (`npx playwright install chromium`). PW_CHANNEL overrides.
 */
const PORT = 3100;
const channel = process.env.PW_CHANNEL ?? (process.platform === "win32" ? "msedge" : undefined);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 }, channel } }],
  webServer: {
    command: `npm run build && npm run start -- -p ${PORT}`,
    url: `http://localhost:${PORT}`,
    // Mock mode whatever a local .env.local says: process env wins over env files.
    env: { NEXT_PUBLIC_API_MODE: "mock" },
    reuseExistingServer: false,
    timeout: 240_000,
  },
});
