import { defineConfig, devices } from "@playwright/test";

// Expects Django on :8000 and Vite on :5173 (CI starts both; locally use docker compose).
export default defineConfig({
  testDir: "./tests",
  retries: process.env.CI ? 1 : 0,
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173", trace: "off" },
  projects: [{ name: "mobile", use: { ...devices["Pixel 7"] } }],
});
