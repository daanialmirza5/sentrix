/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy: { "/v1": "http://127.0.0.1:8000" } },
  // The only chunk over 500 kB is three.js itself, isolated and lazy-loaded (LazyConstellation.tsx).
  build: { chunkSizeWarningLimit: 600 },
  test: { environment: "jsdom", setupFiles: ["./tests/setup.ts"], include: ["tests/**/*.test.tsx"] },
});
