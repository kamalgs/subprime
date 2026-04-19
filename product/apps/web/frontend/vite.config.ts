import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// Vite builds the SPA into /static/dist (served by FastAPI).
// In dev, the Vite server proxies /api/v2 requests to the FastAPI backend.

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: resolve(__dirname, "../static/dist"),
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8091",
      "/static": "http://localhost:8091",
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
  },
});
