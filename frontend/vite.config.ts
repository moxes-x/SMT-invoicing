/// <reference types="vitest/config" />
import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev, Vite proxies /api to Django so cookies stay same-origin (sessions + CSRF, no JWT).
const backend = process.env.VITE_BACKEND_URL ?? "http://localhost:8000";
// /i/, /q/ and /r/ are the customer-facing invoice, quote and receipt pages, rendered by Django.
const proxy = Object.fromEntries(
  ["/api", "/i/", "/q/", "/r/"].map((p) => [p, { target: backend, changeOrigin: false }]),
);

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  server: {
    host: true,
    port: 5173,
    proxy,
  },
  // `pnpm build && pnpm preview` runs the production build (with the offline service worker).
  preview: { host: true, port: 4173, proxy },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
