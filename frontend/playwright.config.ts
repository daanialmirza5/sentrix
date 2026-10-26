import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30000,
  workers: 1,
  reporter: "list",
  use: { baseURL: process.env.SENTRIX_UI ?? "http://localhost:5173", viewport: { width: 1440, height: 900 }, colorScheme: "dark" },
});
