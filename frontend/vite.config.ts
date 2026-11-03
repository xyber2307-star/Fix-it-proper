import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { visualizer } from "rollup-plugin-visualizer";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    process.env.ANALYZE
      ? visualizer({ filename: process.env.ANALYZE, template: "raw-data", gzipSize: true })
      : undefined,
  ],
  build: {
    sourcemap: false,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
