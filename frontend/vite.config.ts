// Vite config. In development the React app runs on :5173 and proxies /api to the FastAPI
// backend on :8000, so the browser only ever talks to one origin.
//
// `vite build --mode static` builds the read-only snapshot for GitHub Pages instead: relative asset
// paths (it works under any repository name), the exported JSON from static-demo/ copied in, and no
// API at all. See `python -m app.cli export-static`.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: mode === "static" ? "./" : "/",
  publicDir: mode === "static" ? "static-demo" : "public",
  build: { outDir: mode === "static" ? "dist-static" : "dist" },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
}));
