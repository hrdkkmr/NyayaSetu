import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run against a running stack (backend on :8000, frontend on :3000).
// Set E2E_BASE_URL to target another environment. Locally the installed Chrome is used
// (PW_CHANNEL=chrome) so no browser download is required; CI installs Chromium.
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    channel: process.env.PW_CHANNEL || undefined,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], channel: process.env.PW_CHANNEL || undefined } },
    { name: "mobile", use: { ...devices["Pixel 7"], channel: process.env.PW_CHANNEL || undefined } },
  ],
});
