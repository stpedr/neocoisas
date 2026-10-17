import { defineConfig, devices } from "@playwright/test";

// E2E ao vivo contra um mestre de verdade (sem mocks): o pytest
// tests/projmap/test_e2e_live_motion.py sobe o mestre e roda este config com
// PROJMAP_LIVE_URL. Não roda no `npm run test:e2e` normal.
export default defineConfig({
  testDir: "./e2e-live",
  reporter: "list",
  timeout: 60_000,
  use: { baseURL: process.env.PROJMAP_LIVE_URL ?? "http://127.0.0.1:8100", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
